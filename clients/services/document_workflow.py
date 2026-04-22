from __future__ import annotations

import logging
from datetime import timedelta
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from django.db import models, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time
from django.utils.translation import gettext as _

from clients.constants import DocumentType
from clients.models import Client, Document, DocumentProcessingJob
from clients.services.activity import changed_field_labels, log_client_activity
from clients.services.document_versions import archive_document_version, replace_document_file
from clients.services.notifications import (
    send_appointment_notification_email,
    send_missing_documents_email,
)
from clients.services.wezwanie_parser import WezwanieData, parse_wezwanie

logger = logging.getLogger(__name__)
DEFAULT_JOB_LEASE_SECONDS = 600
DEFAULT_JOB_MAX_ATTEMPTS = 3

MANUAL_WEZWANIE_REVIEW_MESSAGE = _(
    "Document uploaded, but automatic wezwanie parsing failed. Manual review is required."
)

Parser = Callable[[str], WezwanieData]
NotificationSender = Callable[[Client], int]


@dataclass
class DocumentUploadResult:
    document: Document
    message: str
    manual_review_required: bool = False
    pending_confirmation: bool = False
    parsed_payload: dict[str, str] | None = None


@dataclass
class WezwanieConfirmationResult:
    document: Document
    message: str
    manual_review_required: bool = False


@dataclass
class DocumentProcessingRunResult:
    job: DocumentProcessingJob
    status: str
    processed: bool
    message: str = ""
    manual_review_required: bool = False
    auto_updates: list[str] = field(default_factory=list)


def upload_client_document(
    *,
    client: Client,
    doc_type: str,
    uploaded_document: Document,
    actor,
    parse_requested: bool,
    parser: Parser = parse_wezwanie,
    send_missing_email: NotificationSender = send_missing_documents_email,
    send_appointment_email: NotificationSender = send_appointment_notification_email,
) -> DocumentUploadResult:
    """Persist an uploaded document and route wezwanie handling through services."""

    document = _save_client_document(
        client=client,
        doc_type=doc_type,
        uploaded_document=uploaded_document,
        actor=actor,
    )

    log_client_activity(
        client=client,
        actor=actor,
        event_type="document_uploaded",
        summary=f"Uploaded document: {document.display_name}",
        metadata={"document_id": document.id, "document_type": document.document_type},
        document=document,
    )

    document_type_display = client.get_document_name_by_code(doc_type)
    is_wezwanie = doc_type in (DocumentType.WEZWANIE, DocumentType.WEZWANIE.value)
    if not is_wezwanie:
        return DocumentUploadResult(
            document=document,
            message=_("Document '%(name)s' uploaded successfully.") % {"name": document_type_display},
        )

    if parse_requested:
        return _handle_confirmable_wezwanie_upload(
            document=document,
            client=client,
            document_type_display=document_type_display,
            parser=parser,
        )

    return _handle_background_wezwanie_upload(
        document=document,
        client=client,
        actor=actor,
        document_type_display=document_type_display,
        send_missing_email=send_missing_email,
        send_appointment_email=send_appointment_email,
    )


def confirm_wezwanie_document(
    *,
    document: Document,
    actor,
    confirmation_data: Mapping[str, str],
    parser: Parser = parse_wezwanie,
    send_missing_email: NotificationSender = send_missing_documents_email,
    send_appointment_email: NotificationSender = send_appointment_notification_email,
) -> WezwanieConfirmationResult:
    """Apply confirmed wezwanie fields to the client and trigger follow-up actions."""

    client = document.client
    updated_fields, auto_updates = _apply_confirmation_updates(client, confirmation_data)

    if updated_fields:
        client.save(update_fields=updated_fields)
        log_client_activity(
            client=client,
            actor=actor,
            event_type="client_updated",
            summary="Wezwanie data confirmed",
            details=", ".join(changed_field_labels(client, updated_fields)),
            metadata={"changed_fields": updated_fields, "source": "wezwanie_confirmation"},
            document=document,
        )

    document.awaiting_confirmation = False
    document.save(update_fields=["awaiting_confirmation"])

    manual_review_required = False
    try:
        parsed = parser(document.file.path)
    except Exception:
        logger.exception("Wezwanie parsing failed during confirmation for document %s", document.id)
        manual_review_required = True
    else:
        _append_required_documents_update(parsed, auto_updates)

    if _send_notification(send_missing_email, client, "missing-documents email"):
        auto_updates.append(_("missing-documents email sent"))

    if client.fingerprints_date and _send_notification(
        send_appointment_email,
        client,
        "appointment notification",
    ):
        auto_updates.append(_("appointment notification sent"))

    message = _("Wezwanie data confirmed.")
    if manual_review_required:
        message = f"{message} {MANUAL_WEZWANIE_REVIEW_MESSAGE}"
    if auto_updates:
        message = f"{message} " + " ; ".join(auto_updates)

    return WezwanieConfirmationResult(
        document=document,
        message=message,
        manual_review_required=manual_review_required,
    )


def enqueue_document_processing_job(*, document: Document, actor=None) -> DocumentProcessingJob:
    """Queue background OCR work for the current document file."""

    job_defaults = {
        "created_by": actor if getattr(actor, "is_authenticated", False) else None,
        "status": DocumentProcessingJob.STATUS_PENDING,
        "source_file_name": document.file.name,
        "max_attempts": DEFAULT_JOB_MAX_ATTEMPTS,
        "error_message": "",
        "next_attempt_at": timezone.now(),
        "lease_expires_at": None,
        "started_at": None,
        "completed_at": None,
    }

    with transaction.atomic():
        job, _created = DocumentProcessingJob.objects.update_or_create(
            document=document,
            job_type=DocumentProcessingJob.JOB_TYPE_WEZWANIE_OCR,
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
        job_type=DocumentProcessingJob.JOB_TYPE_WEZWANIE_OCR,
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
    """Run OCR for a queued wezwanie document and persist the result."""

    parser = parser or parse_wezwanie
    send_missing_email = send_missing_email or send_missing_documents_email
    send_appointment_email = send_appointment_email or send_appointment_notification_email

    with transaction.atomic():
        job = (
            DocumentProcessingJob.objects.select_for_update()
            .select_related("document", "document__client", "created_by")
            .get(pk=job_id)
        )
        if job.status != DocumentProcessingJob.STATUS_PENDING:
            return DocumentProcessingRunResult(
                job=job,
                status=job.status,
                processed=False,
                message=_("Job is not pending."),
            )

        source_file_name = job.source_file_name or job.document.file.name
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
        document_path = job.document.file.path

    try:
        parsed = parser(document_path)
    except Exception as exc:
        logger.exception("Automatic wezwanie parsing failed for queued job %s", job_id)
        return _finalize_failed_document_job(
            job_id=job_id,
            source_file_name=source_file_name,
            error_message=str(exc) or _("Automatic wezwanie parsing failed."),
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


def _save_client_document(
    *,
    client: Client,
    doc_type: str,
    uploaded_document: Document,
    actor,
) -> Document:
    existing_doc = Document.objects.filter(client=client, document_type=doc_type).first()
    if not existing_doc:
        uploaded_document.client = client
        uploaded_document.document_type = doc_type
        uploaded_document.save()
        return uploaded_document

    with transaction.atomic():
        archive_document_version(
            existing_doc,
            uploaded_by=actor if getattr(actor, "is_authenticated", False) else None,
            comment=_("Automatic archive before replacing the document file"),
        )
        return replace_document_file(
            existing_doc,
            uploaded_file=uploaded_document.file,
            expiry_date=uploaded_document.expiry_date,
        )


def _handle_confirmable_wezwanie_upload(
    *,
    document: Document,
    client: Client,
    document_type_display: str,
    parser: Parser,
) -> DocumentUploadResult:
    try:
        parsed = parser(document.file.path)
    except Exception:
        logger.exception("Wezwanie parsing failed for document %s", document.id)
        document.ocr_status = "failed"
        document.ocr_name_mismatch = False
        document.awaiting_confirmation = False
        document.save(update_fields=["ocr_status", "ocr_name_mismatch", "awaiting_confirmation"])
        return DocumentUploadResult(
            document=document,
            message=_compose_upload_message(
                document_type_display=document_type_display,
                manual_review_required=True,
            ),
            manual_review_required=True,
        )

    if not _has_meaningful_parsed_data(parsed):
        document.ocr_status = "failed"
        document.ocr_name_mismatch = False
        document.awaiting_confirmation = False
        document.save(update_fields=["ocr_status", "ocr_name_mismatch", "awaiting_confirmation"])
        return DocumentUploadResult(
            document=document,
            message=_compose_upload_message(
                document_type_display=document_type_display,
                manual_review_required=True,
            ),
            manual_review_required=True,
        )

    document.ocr_status = "success"
    document.ocr_name_mismatch = _has_name_mismatch(parsed.full_name, client)
    document.awaiting_confirmation = True
    document.save(update_fields=["awaiting_confirmation", "ocr_status", "ocr_name_mismatch"])

    return DocumentUploadResult(
        document=document,
        message=_("Document uploaded. Please confirm the parsed data."),
        pending_confirmation=True,
        parsed_payload=_build_wezwanie_payload(parsed),
    )


def _handle_background_wezwanie_upload(
    *,
    document: Document,
    client: Client,
    actor,
    document_type_display: str,
    send_missing_email: NotificationSender,
    send_appointment_email: NotificationSender,
) -> DocumentUploadResult:
    del client, send_missing_email, send_appointment_email
    enqueue_document_processing_job(document=document, actor=actor)
    return DocumentUploadResult(
        document=document,
        message=_(
            "Document '%(name)s' uploaded successfully. OCR processing will continue in the background."
        )
        % {"name": document_type_display},
    )


def _finalize_failed_document_job(
    *,
    job_id: int,
    source_file_name: str,
    error_message: str,
) -> DocumentProcessingRunResult:
    with transaction.atomic():
        job = (
            DocumentProcessingJob.objects.select_for_update()
            .select_related("document", "document__client", "created_by")
            .get(pk=job_id)
        )
        document = Document.objects.select_for_update().select_related("client").get(pk=job.document_id)
        if not _job_matches_processing_state(job, document, source_file_name):
            return DocumentProcessingRunResult(
                job=job,
                status="skipped",
                processed=False,
                message=_("Job was superseded by a newer upload."),
            )

        document.ocr_status = "failed"
        document.ocr_name_mismatch = False
        document.awaiting_confirmation = False
        document.save(update_fields=["ocr_status", "ocr_name_mismatch", "awaiting_confirmation"])

        should_retry = job.attempts < job.max_attempts
        job.status = (
            DocumentProcessingJob.STATUS_PENDING
            if should_retry
            else DocumentProcessingJob.STATUS_FAILED
        )
        job.error_message = error_message
        job.completed_at = timezone.now() if not should_retry else None
        job.lease_expires_at = None
        job.next_attempt_at = (
            timezone.now() + timedelta(minutes=2 ** max(job.attempts - 1, 0))
            if should_retry
            else None
        )
        job.save(
            update_fields=[
                "status",
                "error_message",
                "completed_at",
                "lease_expires_at",
                "next_attempt_at",
            ]
        )

    return DocumentProcessingRunResult(
        job=job,
        status=job.status,
        processed=True,
        message=MANUAL_WEZWANIE_REVIEW_MESSAGE if job.status == DocumentProcessingJob.STATUS_FAILED else _("OCR job requeued for retry."),
        manual_review_required=job.status == DocumentProcessingJob.STATUS_FAILED,
    )


def _finalize_successful_document_job(
    *,
    job_id: int,
    source_file_name: str,
    parsed: WezwanieData,
    send_missing_email: NotificationSender,
    send_appointment_email: NotificationSender,
) -> DocumentProcessingRunResult:
    auto_updates: list[str] = []

    with transaction.atomic():
        job = (
            DocumentProcessingJob.objects.select_for_update()
            .select_related("document", "document__client", "created_by")
            .get(pk=job_id)
        )
        document = Document.objects.select_for_update().select_related("client").get(pk=job.document_id)
        if not _job_matches_processing_state(job, document, source_file_name):
            return DocumentProcessingRunResult(
                job=job,
                status="skipped",
                processed=False,
                message=_("Job was superseded by a newer upload."),
            )

        client = Client.objects.select_for_update().get(pk=document.client_id)
        actor = job.created_by

        updated_fields, parsed_updates = _apply_parsed_client_updates(client, parsed)
        auto_updates.extend(parsed_updates)
        _append_required_documents_update(parsed, auto_updates)

        if updated_fields:
            client.save(update_fields=updated_fields)
            log_client_activity(
                client=client,
                actor=actor,
                event_type="client_updated",
                summary="Client data updated from background wezwanie OCR",
                details=", ".join(changed_field_labels(client, updated_fields)),
                metadata={"changed_fields": updated_fields, "source": "document_processing_job"},
                document=document,
            )

        document.ocr_status = "success"
        document.awaiting_confirmation = False
        document.ocr_name_mismatch = _has_name_mismatch(parsed.full_name, client)
        document.save(update_fields=["ocr_status", "awaiting_confirmation", "ocr_name_mismatch"])

        job.status = DocumentProcessingJob.STATUS_COMPLETED
        job.error_message = ""
        job.completed_at = timezone.now()
        job.lease_expires_at = None
        job.next_attempt_at = None
        job.save(update_fields=["status", "error_message", "completed_at", "lease_expires_at", "next_attempt_at"])

    auto_updates.extend(
        _send_background_notifications(
            client=client,
            parsed=parsed,
            send_missing_email=send_missing_email,
            send_appointment_email=send_appointment_email,
        )
    )

    return DocumentProcessingRunResult(
        job=job,
        status=DocumentProcessingJob.STATUS_COMPLETED,
        processed=True,
        message=_("Queued OCR job completed successfully."),
        auto_updates=auto_updates,
    )


def _job_matches_processing_state(
    job: DocumentProcessingJob,
    document: Document,
    source_file_name: str,
) -> bool:
    return (
        job.status == DocumentProcessingJob.STATUS_PROCESSING
        and job.source_file_name == source_file_name
        and document.file.name == source_file_name
    )


def reclaim_stale_document_jobs(*, now=None) -> int:
    now = now or timezone.now()
    stale_jobs = DocumentProcessingJob.objects.filter(
        job_type=DocumentProcessingJob.JOB_TYPE_WEZWANIE_OCR,
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


def _send_background_notifications(
    *,
    client: Client,
    parsed: WezwanieData,
    send_missing_email: NotificationSender,
    send_appointment_email: NotificationSender,
) -> list[str]:
    auto_updates: list[str] = []

    if _send_notification(send_missing_email, client, "missing-documents email"):
        auto_updates.append(_("missing-documents email sent"))

    if parsed.wezwanie_type == "fingerprints" and parsed.fingerprints_date:
        if _send_notification(send_appointment_email, client, "appointment notification"):
            auto_updates.append(_("appointment notification sent"))

    return auto_updates


def _send_notification(sender: NotificationSender, client: Client, label: str) -> bool:
    try:
        return bool(sender(client))
    except Exception:
        logger.exception("Failed to send %s for client %s", label, client.pk)
        return False


def _compose_upload_message(
    *,
    document_type_display: str,
    auto_updates: list[str] | None = None,
    manual_review_required: bool = False,
) -> str:
    message = _("Document '%(name)s' uploaded successfully.") % {"name": document_type_display}
    if manual_review_required:
        message = f"{message} {MANUAL_WEZWANIE_REVIEW_MESSAGE}"
    if auto_updates:
        message = message + " " + " ; ".join(auto_updates)
    return message


def _has_meaningful_parsed_data(parsed: WezwanieData) -> bool:
    return bool(parsed.text.strip()) or any(
        [
            parsed.case_number,
            parsed.fingerprints_date,
            parsed.decision_date,
            parsed.full_name,
        ]
    )


def _has_name_mismatch(parsed_full_name: str | None, client: Client) -> bool:
    if not parsed_full_name or not client.first_name or not client.last_name:
        return False
    normalized_name = parsed_full_name.lower()
    return (
        client.first_name.lower() not in normalized_name
        or client.last_name.lower() not in normalized_name
    )


def _build_wezwanie_payload(parsed: WezwanieData) -> dict[str, str]:
    first_name = ""
    last_name = ""
    if parsed.full_name:
        name_parts = parsed.full_name.split()
        if len(name_parts) >= 2:
            first_name = name_parts[0]
            last_name = " ".join(name_parts[1:])

    return {
        "full_name": parsed.full_name or "",
        "first_name": first_name,
        "last_name": last_name,
        "case_number": parsed.case_number or "",
        "fingerprints_date": parsed.fingerprints_date.isoformat() if parsed.fingerprints_date else "",
        "fingerprints_date_display": parsed.fingerprints_date.strftime("%d.%m.%Y")
        if parsed.fingerprints_date
        else "",
        "fingerprints_time": parsed.fingerprints_time or "",
        "fingerprints_location": parsed.fingerprints_location or "",
        "decision_date": parsed.decision_date.isoformat() if parsed.decision_date else "",
        "decision_date_display": parsed.decision_date.strftime("%d.%m.%Y")
        if parsed.decision_date
        else "",
    }


def _append_required_documents_update(parsed: WezwanieData, auto_updates: list[str]) -> None:
    if not parsed.required_documents:
        return

    doc_labels: list[str] = []
    for doc_code in parsed.required_documents:
        try:
            doc_labels.append(str(DocumentType(doc_code).label))
        except ValueError:
            doc_labels.append(doc_code)

    if doc_labels:
        auto_updates.append(
            _("required documents detected: %(val)s") % {"val": ", ".join(doc_labels)}
        )


def _apply_parsed_client_updates(client: Client, parsed: WezwanieData) -> tuple[list[str], list[str]]:
    updated_fields: list[str] = []
    auto_updates: list[str] = []

    if parsed.case_number and parsed.case_number != client.case_number:
        client.case_number = parsed.case_number
        updated_fields.append("case_number")
        auto_updates.append(_("case number: %(val)s") % {"val": parsed.case_number})

    if parsed.fingerprints_date and parsed.fingerprints_date != client.fingerprints_date:
        client.fingerprints_date = parsed.fingerprints_date
        updated_fields.append("fingerprints_date")
        auto_updates.append(
            _("fingerprints date: %(val)s")
            % {"val": parsed.fingerprints_date.strftime("%d.%m.%Y")}
        )

    parsed_fingerprints_time = parse_time(parsed.fingerprints_time or "")
    if parsed_fingerprints_time and parsed_fingerprints_time != client.fingerprints_time:
        client.fingerprints_time = parsed_fingerprints_time
        updated_fields.append("fingerprints_time")

    if parsed.fingerprints_location and parsed.fingerprints_location != (client.fingerprints_location or ""):
        client.fingerprints_location = parsed.fingerprints_location
        updated_fields.append("fingerprints_location")

    if parsed.decision_date and parsed.decision_date != client.decision_date:
        client.decision_date = parsed.decision_date
        updated_fields.append("decision_date")
        auto_updates.append(
            _("decision date: %(val)s") % {"val": parsed.decision_date.strftime("%d.%m.%Y")}
        )

    if parsed.full_name and (not client.first_name or not client.last_name):
        name_parts = parsed.full_name.split()
        if len(name_parts) >= 2:
            client.first_name = name_parts[0]
            client.last_name = " ".join(name_parts[1:])
            updated_fields.extend(["first_name", "last_name"])
            auto_updates.append(_("full name: %(val)s") % {"val": parsed.full_name})

    return updated_fields, auto_updates


def _apply_confirmation_updates(
    client: Client,
    confirmation_data: Mapping[str, str],
) -> tuple[list[str], list[str]]:
    updated_fields: list[str] = []
    auto_updates: list[str] = []

    first_name = (confirmation_data.get("first_name") or "").strip()
    last_name = (confirmation_data.get("last_name") or "").strip()
    case_number = (confirmation_data.get("case_number") or "").strip()
    fingerprints_date_raw = (confirmation_data.get("fingerprints_date") or "").strip()
    fingerprints_time_raw = (confirmation_data.get("fingerprints_time") or "").strip()
    fingerprints_location = (confirmation_data.get("fingerprints_location") or "").strip()
    decision_date_raw = (confirmation_data.get("decision_date") or "").strip()

    if first_name and first_name != client.first_name:
        client.first_name = first_name
        updated_fields.append("first_name")

    if last_name and last_name != client.last_name:
        client.last_name = last_name
        updated_fields.append("last_name")

    if case_number and case_number != client.case_number:
        client.case_number = case_number
        updated_fields.append("case_number")
        auto_updates.append(_("case number: %(val)s") % {"val": case_number})

    fingerprints_date = parse_date(fingerprints_date_raw) if fingerprints_date_raw else None
    if fingerprints_date and fingerprints_date != client.fingerprints_date:
        client.fingerprints_date = fingerprints_date
        updated_fields.append("fingerprints_date")
        auto_updates.append(
            _("fingerprints date: %(val)s") % {"val": fingerprints_date.strftime("%d.%m.%Y")}
        )

    fingerprints_time = parse_time(fingerprints_time_raw) if fingerprints_time_raw else None
    if fingerprints_time and fingerprints_time != client.fingerprints_time:
        client.fingerprints_time = fingerprints_time
        updated_fields.append("fingerprints_time")

    if fingerprints_location and fingerprints_location != (client.fingerprints_location or ""):
        client.fingerprints_location = fingerprints_location
        updated_fields.append("fingerprints_location")

    decision_date = parse_date(decision_date_raw) if decision_date_raw else None
    if decision_date and decision_date != client.decision_date:
        client.decision_date = decision_date
        updated_fields.append("decision_date")
        auto_updates.append(
            _("decision date: %(val)s") % {"val": decision_date.strftime("%d.%m.%Y")}
        )

    return updated_fields, auto_updates
