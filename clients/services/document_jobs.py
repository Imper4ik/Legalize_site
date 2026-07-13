"""Document OCR job queue: enqueue, dispatch, reclaim.

Extracted from ``document_workflow``. The per-type processors live in
``document_job_processors``; the upload facade stays in ``document_workflow``.
"""
from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from clients.models import Document, DocumentProcessingJob
from clients.services.document_processing_common import (
    DEFAULT_JOB_LEASE_SECONDS,
    DEFAULT_JOB_MAX_ATTEMPTS,
    DocumentProcessingRunResult,
    NotificationSender,
    Parser,
    _document_file_identity,
)
from clients.services.document_workflow_wezwanie import (
    _has_meaningful_parsed_data,
)
from clients.services.notifications import (
    send_appointment_notification_email,
    send_missing_documents_email,
)
from clients.services.wezwanie_parser import parse_wezwanie

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

from clients.services.document_job_processors import (
    _finalize_failed_document_job,
    _finalize_successful_document_job,
    _process_company_doc_job_internal,
    _process_insurance_doc_job_internal,
    _process_passport_doc_job_internal,
    _process_rental_doc_job_internal,
    _process_zus_doc_job_internal,
)

logger = logging.getLogger(__name__)


def enqueue_document_processing_job(
    *,
    document: Document,
    actor: AbstractBaseUser | AnonymousUser | None = None,
    requires_confirmation: bool = False,
    job_type: str = DocumentProcessingJob.JOB_TYPE_WEZWANIE_OCR,
) -> DocumentProcessingJob:
    """Queue background OCR work for the current document file."""

    job_defaults = {
        "created_by": actor if actor and actor.is_authenticated else None,
        "status": DocumentProcessingJob.STATUS_PENDING,
        "source_file_name": _document_file_identity(document),
        "max_attempts": DEFAULT_JOB_MAX_ATTEMPTS,
        "error_message": "",
        "next_attempt_at": timezone.now(),
        "lease_expires_at": None,
        "started_at": None,
        "completed_at": None,
        "requires_confirmation": requires_confirmation,
    }

    with transaction.atomic():
        job, _created = DocumentProcessingJob.objects.update_or_create(
            document=document,
            job_type=job_type,
            defaults=job_defaults,
        )
        document.awaiting_confirmation = False
        document.ocr_status = "pending"
        document.ocr_name_mismatch = False
        document.save(update_fields=["awaiting_confirmation", "ocr_status", "ocr_name_mismatch"])

    return job


def process_pending_document_jobs(
    *,
    limit: int | None = None,
    parser: Parser | None = None,
    send_missing_email: NotificationSender | None = None,
    send_appointment_email: NotificationSender | None = None,
) -> list[DocumentProcessingRunResult]:
    """Process queued OCR jobs in FIFO order."""
    reclaim_stale_document_jobs()

    now = timezone.now()

    queryset = DocumentProcessingJob.objects.filter(
        status=DocumentProcessingJob.STATUS_PENDING,
        attempts__lt=models.F("max_attempts"),
    ).filter(
        models.Q(next_attempt_at__isnull=True) | models.Q(next_attempt_at__lte=now)
    ).order_by("created_at")

    if limit is not None:
        queryset = queryset[:limit]

    job_ids = list(queryset.values_list("id", flat=True))
    return [
        process_document_processing_job(
            job_id=job_id,
            parser=parser,
            send_missing_email=send_missing_email,
            send_appointment_email=send_appointment_email,
        )
        for job_id in job_ids
    ]


def process_document_processing_job(
    *,
    job_id: int,
    parser: Parser | None = None,
    send_missing_email: NotificationSender | None = None,
    send_appointment_email: NotificationSender | None = None,
) -> DocumentProcessingRunResult:
    """Run OCR for a queued document and persist the result."""

    parser = parser or parse_wezwanie
    send_missing_email = send_missing_email or send_missing_documents_email
    send_appointment_email = send_appointment_email or send_appointment_notification_email

    with transaction.atomic():
        job = (
            DocumentProcessingJob.objects.select_for_update()
            .select_related("document", "document__client")
            .get(pk=job_id)
        )
        if job.status != DocumentProcessingJob.STATUS_PENDING:
            return DocumentProcessingRunResult(
                job=job,
                status=job.status,
                processed=False,
                message=_("Job is not pending."),
            )

        source_file_name = job.source_file_name or _document_file_identity(job.document)
        job.status = DocumentProcessingJob.STATUS_PROCESSING
        job.attempts += 1
        job.started_at = timezone.now()
        job.lease_expires_at = job.started_at + timedelta(seconds=DEFAULT_JOB_LEASE_SECONDS)
        job.error_message = ""
        job.completed_at = None
        job.save(
            update_fields=[
                "status",
                "attempts",
                "started_at",
                "lease_expires_at",
                "error_message",
                "completed_at",
            ]
        )
        document_file = job.document.file

    if job.job_type == DocumentProcessingJob.JOB_TYPE_COMPANY_DOC_OCR:
        return _process_company_doc_job_internal(job, source_file_name, document_file)
    elif job.job_type == DocumentProcessingJob.JOB_TYPE_PASSPORT_OCR:
        return _process_passport_doc_job_internal(job, source_file_name, document_file)
    elif job.job_type == DocumentProcessingJob.JOB_TYPE_RENTAL_OCR:
        return _process_rental_doc_job_internal(job, source_file_name, document_file)
    elif job.job_type == DocumentProcessingJob.JOB_TYPE_ZUS_OCR:
        return _process_zus_doc_job_internal(job, source_file_name, document_file)
    elif job.job_type == DocumentProcessingJob.JOB_TYPE_INSURANCE_OCR:
        return _process_insurance_doc_job_internal(job, source_file_name, document_file)

    try:
        with document_file.open("rb") as src:
            ext = os.path.splitext(document_file.name or "")[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                for chunk in src.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
        try:
            parsed = parser(tmp_path)
        finally:
            os.remove(tmp_path)
    except Exception as exc:
        logger.warning(
            "Automatic wezwanie parsing failed for queued job %s: error_type=%s",
            job_id,
            type(exc).__name__,
        )
        return _finalize_failed_document_job(
            job_id=job_id,
            source_file_name=source_file_name,
            error_message=_("Automatic wezwanie parsing failed."),
        )

    if not _has_meaningful_parsed_data(parsed):
        return _finalize_failed_document_job(
            job_id=job_id,
            source_file_name=source_file_name,
            error_message=_("Parsed wezwanie data was empty."),
        )

    return _finalize_successful_document_job(
        job_id=job_id,
        source_file_name=source_file_name,
        parsed=parsed,
        send_missing_email=send_missing_email,
        send_appointment_email=send_appointment_email,
    )



def reclaim_stale_document_jobs(*, now: datetime | None = None) -> int:
    now = now or timezone.now()
    stale_jobs = DocumentProcessingJob.objects.filter(
        status=DocumentProcessingJob.STATUS_PROCESSING,
        lease_expires_at__isnull=False,
        lease_expires_at__lt=now,
    )
    updated = 0
    for job in stale_jobs.iterator():
        job.status = (
            DocumentProcessingJob.STATUS_PENDING
            if job.attempts < job.max_attempts
            else DocumentProcessingJob.STATUS_FAILED
        )
        job.error_message = _("Job lease expired before completion.")
        job.completed_at = timezone.now() if job.status == DocumentProcessingJob.STATUS_FAILED else None
        job.next_attempt_at = now if job.status == DocumentProcessingJob.STATUS_PENDING else None
        job.lease_expires_at = None
        job.save(update_fields=["status", "error_message", "completed_at", "next_attempt_at", "lease_expires_at"])
        updated += 1
    return updated
