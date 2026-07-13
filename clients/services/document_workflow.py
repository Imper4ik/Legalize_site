from __future__ import annotations

import logging
import os
import re
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import TYPE_CHECKING, Any, cast

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from clients.constants import DocumentType
from clients.models import Case, Client, Document, DocumentProcessingJob
from clients.services.activity import log_client_activity
from clients.services.company_parser import parse_company_doc
from clients.services.document_workflow_wezwanie import (
    _append_required_documents_update,
    _apply_confirmation_updates,
    _apply_parsed_client_updates,
    _build_confirmed_wezwanie_notification_data,
    _build_confirmed_wezwanie_payload,
    _build_wezwanie_payload,
    _has_meaningful_parsed_data,
    _has_name_mismatch,
)
from clients.services.document_workflow_zus import (
    _build_zus_month_status,
    _format_month,
    _normalize_month,
    _safe_assign_zus_month,
)
from clients.services.notifications import (
    send_appointment_notification_email,
    send_missing_documents_email,
)
from clients.services.registry_api import match_names, normalize_string, verify_employer
from clients.services.wezwanie_parser import WezwanieData, parse_wezwanie

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

logger = logging.getLogger(__name__)
DEFAULT_JOB_LEASE_SECONDS = 600
DEFAULT_JOB_MAX_ATTEMPTS = 3

MANUAL_WEZWANIE_REVIEW_MESSAGE = _(
    "Document uploaded, but automatic wezwanie parsing failed. Manual review is required."
)

Parser = Callable[[str], WezwanieData]
# Senders are called as ``sender(client)`` and, when supported, ``sender(client,
# case=...)``; ``_send_notification`` falls back on TypeError. Use an open
# signature so the optional keyword is well-typed.
NotificationSender = Callable[..., int]


def _document_file_identity(document: Document) -> str:
    """Stable non-PII token used to detect whether a queued file changed."""

    source_name = document.file.name or ""
    if not source_name:
        return ""
    return sha256(source_name.encode("utf-8")).hexdigest()


@dataclass
class DocumentUploadResult:
    document: Document
    message: str
    manual_review_required: bool = False
    pending_confirmation: bool = False
    ocr_processing_queued: bool = False
    parsed_payload: dict[str, Any] | None = None


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


def _resolve_proof_submission_from_qr(client: Client, case: Case | None, document: Document) -> Any:
    """Decode the cover-sheet QR marker (if any) to link the stamp to the exact
    submission it was printed for. Returns ``None`` when the marker is missing,
    unreadable, or points at a submission outside this client/case scope, so the
    caller falls back to the latest-submission heuristic."""
    from clients.models.wniosek import WniosekSubmission
    from clients.services.proof_qr import decode_proof_submission_id

    try:
        name = (document.file.name or "").lower()
        with document.file.open("rb") as handle:
            file_bytes = handle.read()
    except Exception as exc:  # pragma: no cover - defensive I/O guard
        logger.info("Could not read proof file for QR decode: %s", exc)
        return None

    submission_id = decode_proof_submission_id(file_bytes, is_pdf=name.endswith(".pdf"))
    if submission_id is None:
        return None

    queryset = WniosekSubmission.objects.filter(pk=submission_id, client=client)
    case_id = getattr(case, "pk", None)
    if case_id is not None:
        queryset = queryset.filter(case_id=case_id)
    return queryset.first()


def _resolve_confirmed_submission(client: Client, case: Case | None) -> Any:
    """Pick the submission a freshly uploaded proof-of-submission stamp confirms.

    Defaults to the most recent Wniosek submission for the case (falling back to
    the client when no case is scoped), which matches the real workflow: staff
    print the cover sheet, submit the package, get it stamped, then upload it."""
    from clients.models.wniosek import WniosekSubmission

    queryset = WniosekSubmission.objects.filter(client=client)
    case_id = getattr(case, "pk", None)
    if case_id is not None:
        queryset = queryset.filter(case_id=case_id)
    return queryset.order_by("-confirmed_at", "-id").first()


def upload_client_document(
    *,
    client: Client,
    doc_type: str,
    uploaded_document: Document,
    actor: AbstractBaseUser | AnonymousUser | None,
    parse_requested: bool,
    case: Case | None = None,
    parser: Parser = parse_wezwanie,
    send_missing_email: NotificationSender = send_missing_documents_email,
    send_appointment_email: NotificationSender = send_appointment_notification_email,
    confirms_submission: Any = None,
) -> DocumentUploadResult:
    """Persist an uploaded document and route wezwanie handling through services.

    ``case`` scopes the document to a specific case (spec section 1/5). When
    omitted the Document model falls back to the client's single active case;
    portal callers must always pass it so a multi-case client cannot trigger the
    ambiguous legacy fallback.

    ``confirms_submission`` links a proof-of-submission stamp to the submission
    whose checklist positions it closes; when omitted for that document type the
    latest submission for the case is resolved automatically.
    """

    document = _save_client_document(
        client=client,
        doc_type=doc_type,
        uploaded_document=uploaded_document,
        actor=actor,
        case=case,
    )

    from clients.constants import is_proof_of_submission_document_type

    if is_proof_of_submission_document_type(doc_type):
        submission = confirms_submission or _resolve_proof_submission_from_qr(client, case, document)
        submission = submission or _resolve_confirmed_submission(client, case)
        if submission is not None and document.confirms_submission_id != submission.pk:
            document.confirms_submission = submission
            document.save(update_fields=["confirms_submission"])

    if not actor or not getattr(actor, "is_staff", False):
        from clients.constants import is_wezwanie_document_type
        from clients.services.tasks import create_auto_task
        if not is_wezwanie_document_type(doc_type):
            create_auto_task(client, "document_review", document=document)

    log_client_activity(
        client=client,
        actor=actor,
        event_type="document_uploaded",
        summary="Uploaded document",
        metadata={"document_id": document.id},
        document=document,
    )

    document_type_display = client.get_document_name_by_code(doc_type)
    from clients.constants import (
        is_company_document_type,
        is_insurance_document_type,
        is_passport_document_type,
        is_rental_document_type,
        is_wezwanie_document_type,
        is_zus_document_type,
    )
    is_wezwanie = is_wezwanie_document_type(doc_type)
    is_company = is_company_document_type(doc_type)
    is_passport = is_passport_document_type(doc_type)
    is_rental = is_rental_document_type(doc_type)
    is_zus = is_zus_document_type(doc_type)
    is_insurance = is_insurance_document_type(doc_type)

    is_ocr_eligible = is_wezwanie or is_company or is_passport or is_rental or is_zus or is_insurance

    if not is_ocr_eligible:
        return DocumentUploadResult(
            document=document,
            message=_("Document '%(name)s' uploaded successfully.") % {"name": document_type_display},
        )

    if parse_requested or is_company or is_passport or is_rental or is_zus or is_insurance:
        # Determine job type
        if is_company:
            job_type = DocumentProcessingJob.JOB_TYPE_COMPANY_DOC_OCR
        elif is_passport:
            job_type = DocumentProcessingJob.JOB_TYPE_PASSPORT_OCR
        elif is_rental:
            job_type = DocumentProcessingJob.JOB_TYPE_RENTAL_OCR
        elif is_zus:
            is_zus_rca_with_month = (
                doc_type == DocumentType.ZUS_RCA_OR_INSURANCE.value and bool(document.zus_period_month)
            )
            job_type = (
                DocumentProcessingJob.JOB_TYPE_ZUS_OCR
                if is_zus_rca_with_month or doc_type == DocumentType.ZUS_CONTRIBUTION_HISTORY.value
                else DocumentProcessingJob.JOB_TYPE_INSURANCE_OCR
            )
        elif is_insurance:
            job_type = DocumentProcessingJob.JOB_TYPE_INSURANCE_OCR
        else:
            job_type = DocumentProcessingJob.JOB_TYPE_WEZWANIE_OCR

        requires_confirmation = (job_type == DocumentProcessingJob.JOB_TYPE_WEZWANIE_OCR)
        job = enqueue_document_processing_job(
            document=document,
            actor=actor,
            requires_confirmation=requires_confirmation,
            job_type=job_type,
        )

        if not getattr(settings, "ASYNC_OCR_PROCESSING", False):
            if not requires_confirmation:
                return _process_company_upload_job_inline(
                    job_id=job.pk,
                    document=document,
                    document_type_display=document_type_display,
                )
            else:
                return _process_upload_job_inline(
                    job_id=job.pk,
                    document=document,
                    document_type_display=document_type_display,
                    parser=parser,
                    send_missing_email=send_missing_email,
                    send_appointment_email=send_appointment_email,
                )

        msg = (
            _("Document uploaded. OCR and automatic verification were queued; review details after processing completes.")
            if not requires_confirmation
            else _("Document uploaded. OCR processing was queued; review recognized data after processing completes.")
        )
        return DocumentUploadResult(
            document=document,
            message=msg,
            ocr_processing_queued=True,
        )

    return DocumentUploadResult(
        document=document,
        message=_("Document '%(name)s' uploaded successfully.") % {"name": document_type_display},
    )


def confirm_wezwanie_document(
    *,
    document: Document,
    actor: AbstractBaseUser | AnonymousUser | None,
    confirmation_data: Mapping[str, str],
    parser: Parser = parse_wezwanie,
    send_missing_email: NotificationSender = send_missing_documents_email,
    send_appointment_email: NotificationSender = send_appointment_notification_email,
) -> WezwanieConfirmationResult:
    """Validate, persist and update metadata following confirmation of a wezwanie."""

    from clients.constants import is_wezwanie_document_type
    if not is_wezwanie_document_type(document.document_type):
        return WezwanieConfirmationResult(
            document=document,
            message=_("Selected document type cannot be confirmed as a wezwanie."),
            manual_review_required=True,
        )

    payload = _build_confirmed_wezwanie_payload(confirmation_data)

    with transaction.atomic():
        document.awaiting_confirmation = False
        document.parsed_data = payload
        document.ocr_status = "success"
        document.save(update_fields=["awaiting_confirmation", "parsed_data", "ocr_status"])

    client = document.client
    case = document.case if document.case_id else None
    case_fields, client_fields, auto_updates = _apply_confirmation_updates(
        case,
        client,
        confirmation_data,
        actor=actor,
    )
    if case is not None and case_fields:
        case.save(update_fields=case_fields)
        log_client_activity(
            client=client,
            case=case,
            actor=actor,
            event_type="case_updated",
            summary="Case updated from confirmed wezwanie data",
            metadata={"case_id": str(case.uuid), "changed_fields": case_fields},
            document=document,
        )
    if client_fields:
        client.save(update_fields=client_fields)

    log_client_activity(
        client=client,
        case=case,
        actor=actor,
        event_type="document_confirmed",
        summary="Confirmed wezwanie data",
        metadata={
            "document_id": document.id,
            **({"case_id": str(case.uuid)} if case else {}),
        },
        document=document,
    )

    notification_data = _build_confirmed_wezwanie_notification_data(confirmation_data)
    auto_updates.extend(
        _send_background_notifications(
            client=client,
            case=case,
            parsed=notification_data,
            send_missing_email=send_missing_email,
            send_appointment_email=send_appointment_email,
        )
    )

    document_type_display = client.get_document_name_by_code(document.document_type)
    return WezwanieConfirmationResult(
        document=document,
        message=_compose_upload_message(
            document_type_display=document_type_display,
            auto_updates=auto_updates,
            manual_review_required=False,
        ),
    )


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


def _process_company_upload_job_inline(
    *,
    job_id: int,
    document: Document,
    document_type_display: str,
) -> DocumentUploadResult:
    result = process_document_processing_job(job_id=job_id)
    document.refresh_from_db()

    manual_review_required = result.manual_review_required or document.ocr_status == "failed"
    return DocumentUploadResult(
        document=document,
        message=_("Document '%(name)s' uploaded and verified: %(msg)s") % {
            "name": document_type_display,
            "msg": result.message,
        },
        manual_review_required=manual_review_required,
        parsed_payload=document.parsed_data or {},
    )


def _process_company_doc_job_internal(
    job: DocumentProcessingJob,
    source_file_name: str,
    document_file: Any,
) -> DocumentProcessingRunResult:
    try:
        with document_file.open("rb") as src:
            ext = os.path.splitext(document_file.name or "")[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                for chunk in src.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
        try:
            parsed = parse_company_doc(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as exc:
        logger.warning(
            "Automatic company doc parsing failed for queued job %s: error_type=%s",
            job.id,
            type(exc).__name__,
        )
        return _finalize_failed_company_job(
            job_id=job.id,
            source_file_name=source_file_name,
            error_message=str(_("Automatic company doc parsing failed.")),
        )

    # Call registry verification
    try:
        report = verify_employer(
            nip=parsed.nip,
            krs=parsed.krs,
            detected_names=parsed.detected_names,
        )
    except Exception as exc:
        logger.warning(
            "Registry verification failed for job %s: error_type=%s",
            job.id,
            type(exc).__name__,
        )
        report = {
            "registry_source": None,
            "company_name": None,
            "is_employer_active": False,
            "nip": parsed.nip,
            "krs": parsed.krs,
            "representatives": [],
            "signer_authorized": False,
            "matched_signer": None,
            "warnings": [f"Registry query failed with error: {str(exc)}"]
        }

    # Minimum salary check (4300 PLN as of 2026)
    MIN_SALARY = 4300.0
    if parsed.salary is not None:
        if parsed.salary < MIN_SALARY:
            report["warnings"].append(
                str(_("Salary %(salary)s PLN is below the statutory minimum of %(min)s PLN.") % {
                    "salary": parsed.salary,
                    "min": MIN_SALARY
                })
            )
    else:
        report["warnings"].append(str(_("Could not extract salary from the document.")))

    parsed_payload = {
        "nip": parsed.nip,
        "krs": parsed.krs,
        "salary": parsed.salary,
        "valid_until": parsed.valid_until.isoformat() if parsed.valid_until else None,
        "detected_names": parsed.detected_names,
        "registry_verification": report,
        "has_name_mismatch": not report.get("signer_authorized", True),
    }


    return _finalize_successful_company_job(
        job_id=job.id,
        source_file_name=source_file_name,
        parsed_payload=parsed_payload,
        warnings=report["warnings"],
    )


def _finalize_failed_company_job(
    *,
    job_id: int,
    source_file_name: str,
    error_message: str,
) -> DocumentProcessingRunResult:
    with transaction.atomic():
        job = DocumentProcessingJob.objects.select_for_update().get(pk=job_id)
        job.status = DocumentProcessingJob.STATUS_FAILED
        job.error_message = error_message
        job.completed_at = timezone.now()
        job.source_file_name = source_file_name
        job.save(update_fields=["status", "error_message", "completed_at", "source_file_name"])

        document = job.document
        document.ocr_status = "failed"
        document.save(update_fields=["ocr_status"])

    return DocumentProcessingRunResult(
        job=job,
        status=DocumentProcessingJob.STATUS_FAILED,
        processed=False,
        message=error_message,
        manual_review_required=True,
    )


def _finalize_successful_company_job(
    *,
    job_id: int,
    source_file_name: str,
    parsed_payload: dict[str, Any],
    warnings: list[str],
) -> DocumentProcessingRunResult:
    with transaction.atomic():
        job = DocumentProcessingJob.objects.select_for_update().get(pk=job_id)
        job.status = DocumentProcessingJob.STATUS_COMPLETED
        job.completed_at = timezone.now()
        job.error_message = ""
        job.source_file_name = source_file_name
        job.save(update_fields=["status", "completed_at", "error_message", "source_file_name"])

        document = job.document
        document.parsed_data = parsed_payload
        document.ocr_status = "success"
        document.ocr_name_mismatch = bool(warnings)
        document.save(update_fields=["parsed_data", "ocr_status", "ocr_name_mismatch"])

    msg = (
        _("Company document verified successfully with %(warning_count)s warnings.") % {
            "warning_count": len(warnings)
        }
        if warnings else
        _("Company document verified successfully.")
    )
    return DocumentProcessingRunResult(
        job=job,
        status=DocumentProcessingJob.STATUS_COMPLETED,
        processed=True,
        message=msg,
        manual_review_required=bool(warnings),
    )


def _finalize_failed_ocr_job(
    *,
    job_id: int,
    source_file_name: str,
    error_message: str,
) -> DocumentProcessingRunResult:
    with transaction.atomic():
        job = DocumentProcessingJob.objects.select_for_update().get(pk=job_id)
        job.status = DocumentProcessingJob.STATUS_FAILED
        job.error_message = error_message
        job.completed_at = timezone.now()
        job.source_file_name = source_file_name
        job.save(update_fields=["status", "error_message", "completed_at", "source_file_name"])

        document = job.document
        document.ocr_status = "failed"
        document.save(update_fields=["ocr_status"])

    return DocumentProcessingRunResult(
        job=job,
        status=DocumentProcessingJob.STATUS_FAILED,
        processed=False,
        message=error_message,
        manual_review_required=True,
    )


def _finalize_successful_ocr_job(
    *,
    job_id: int,
    source_file_name: str,
    parsed_payload: dict[str, Any],
    warnings: list[str],
    doc_type_display: str,
) -> DocumentProcessingRunResult:
    with transaction.atomic():
        job = DocumentProcessingJob.objects.select_for_update().get(pk=job_id)
        job.status = DocumentProcessingJob.STATUS_COMPLETED
        job.completed_at = timezone.now()
        job.error_message = ""
        job.source_file_name = source_file_name
        job.save(update_fields=["status", "completed_at", "error_message", "source_file_name"])

        document = job.document
        document.parsed_data = parsed_payload
        document.ocr_status = "success"
        document.ocr_name_mismatch = bool(warnings)
        document.scrub_parsed_pii()
        document.save(update_fields=["parsed_data", "ocr_status", "ocr_name_mismatch"])

    if job.job_type == DocumentProcessingJob.JOB_TYPE_PASSPORT_OCR:
        try:
            from clients.models import MOSApplicationData
            from clients.services.intake_extraction import pre_fill_mos_data_from_ocr
            # OCR of a document must only touch its own case's MOS data.
            mos_data = (
                MOSApplicationData.objects.filter(case=document.case).first()
                if document.case_id
                else None
            )
            if mos_data:
                pre_fill_mos_data_from_ocr(mos_data)
        except Exception as exc:
            logger.warning("Failed to auto-fill mos data from parsed passport: %s", exc)

    msg = (
        _("%(doc_type)s verified with %(warning_count)s warnings.") % {
            "doc_type": doc_type_display,
            "warning_count": len(warnings)
        }
        if warnings else
        _("%(doc_type)s verified successfully.") % {"doc_type": doc_type_display}
    )
    return DocumentProcessingRunResult(
        job=job,
        status=DocumentProcessingJob.STATUS_COMPLETED,
        processed=True,
        message=msg,
        manual_review_required=bool(warnings),
    )


def _check_client_name_in_document(client: Client, detected_names: list[str], text: str) -> bool:
    """
    Checks if client's name matches one of the detected names,
    or if both first name and last name are found in the text.
    """
    client_full_name = client.get_full_name()
    if detected_names:
        matched = match_names(detected_names, [client_full_name])
        if matched:
            return True

    # Fallback check on raw text
    norm_text = normalize_string(text)
    norm_first = normalize_string(client.first_name)
    norm_last = normalize_string(client.last_name)
    if norm_first and norm_last:
        if norm_first in norm_text and norm_last in norm_text:
            return True
    return False


def _process_passport_doc_job_internal(
    job: DocumentProcessingJob,
    source_file_name: str,
    document_file: Any,
) -> DocumentProcessingRunResult:
    from clients.services.passport_parser import parse_passport_doc

    try:
        with document_file.open("rb") as src:
            ext = os.path.splitext(document_file.name or "")[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                for chunk in src.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
        try:
            parsed = parse_passport_doc(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as exc:
        logger.warning(
            "Automatic passport parsing failed for queued job %s: error_type=%s",
            job.id,
            type(exc).__name__,
        )
        return _finalize_failed_ocr_job(
            job_id=job.id,
            source_file_name=source_file_name,
            error_message=str(_("Automatic passport parsing failed.")),
        )

    if parsed.error == "no_text":
        return _finalize_failed_ocr_job(
            job_id=job.id,
            source_file_name=source_file_name,
            error_message=str(_("Could not extract any text from the passport.")),
        )

    client = job.document.client
    warnings = []
    auto_updates = []

    # 1. Verify Name
    passport_names = []
    if parsed.first_name and parsed.last_name:
        passport_names.append(f"{parsed.first_name} {parsed.last_name}")

    name_matched = _check_client_name_in_document(client, passport_names, parsed.text)
    if not name_matched:
        warnings.append(str(_("Client name not matched in the passport.")))

    # 2. Verify DOB
    if parsed.date_of_birth and client.birth_date:
        if parsed.date_of_birth != client.birth_date:
            warnings.append(
                str(_("Passport Date of Birth (%(passport_dob)s) does not match Client DOB (%(client_dob)s).") % {
                    "passport_dob": parsed.date_of_birth.isoformat(),
                    "client_dob": client.birth_date.isoformat(),
                })
            )
    elif not parsed.date_of_birth:
        warnings.append(str(_("Could not extract Date of Birth from the passport.")))

    # 3. Verify validity/expiry
    if parsed.valid_until:
        if parsed.valid_until < date.today():
            warnings.append(
                str(_("Passport has expired on %(expiry)s.") % {"expiry": parsed.valid_until.isoformat()})
            )
        elif parsed.valid_until <= date.today() + timedelta(days=90):
            warnings.append(
                str(_("Passport expires soon (%(expiry)s), in less than 3 months.") % {"expiry": parsed.valid_until.isoformat()})
            )
    else:
        warnings.append(str(_("Could not extract Passport expiration date.")))

    # 4. Auto-update passport number if missing in DB
    if parsed.passport_number:
        passport_num_clean = re.sub(r"\s+", "", parsed.passport_number).upper()
        if not client.passport_num:
            client.passport_num = passport_num_clean
            client.save(update_fields=["passport_num"])
            auto_updates.append(f"Updated missing client passport number to: {passport_num_clean}")
        elif client.passport_num.replace(" ", "").upper() != passport_num_clean:
            warnings.append(
                str(_("Passport number in document (%(doc_num)s) does not match profile (%(profile_num)s).") % {
                    "doc_num": passport_num_clean,
                    "profile_num": client.passport_num,
                })
            )

    parsed_payload = {
        "passport_number": parsed.passport_number,
        "first_name": parsed.first_name,
        "last_name": parsed.last_name,
        "date_of_birth": parsed.date_of_birth.isoformat() if parsed.date_of_birth else None,
        "valid_until": parsed.valid_until.isoformat() if parsed.valid_until else None,
        "country": parsed.country,
        "warnings": warnings,
        "auto_updates": auto_updates,
        "has_name_mismatch": not name_matched,
    }

    return _finalize_successful_ocr_job(
        job_id=job.id,
        source_file_name=source_file_name,
        parsed_payload=parsed_payload,
        warnings=warnings,
        doc_type_display=str(_("Passport")),
    )


def _process_rental_doc_job_internal(
    job: DocumentProcessingJob,
    source_file_name: str,
    document_file: Any,
) -> DocumentProcessingRunResult:
    from clients.services.rental_parser import parse_rental_doc

    try:
        with document_file.open("rb") as src:
            ext = os.path.splitext(document_file.name or "")[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                for chunk in src.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
        try:
            parsed = parse_rental_doc(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as exc:
        logger.warning(
            "Automatic rental agreement parsing failed for queued job %s: error_type=%s",
            job.id,
            type(exc).__name__,
        )
        return _finalize_failed_ocr_job(
            job_id=job.id,
            source_file_name=source_file_name,
            error_message=str(_("Automatic rental agreement parsing failed.")),
        )

    if parsed.error == "no_text":
        return _finalize_failed_ocr_job(
            job_id=job.id,
            source_file_name=source_file_name,
            error_message=str(_("Could not extract any text from the rental agreement.")),
        )

    client = job.document.client
    warnings = []

    # 1. Verify Name
    name_matched = _check_client_name_in_document(client, parsed.detected_names, parsed.text)
    if not name_matched:
        warnings.append(str(_("Client name not matched in the rental agreement.")))

    # 2. Verify Address (case-scoped: only this document's case MOS data)
    from clients.models import MOSApplicationData
    mos_data = (
        MOSApplicationData.objects.filter(case=job.document.case).first()
        if job.document.case_id
        else None
    )
    if mos_data and mos_data.address_data:
        address_data = cast("dict[str, Any]", mos_data.address_data)
        street = address_data.get("street", "").strip()
        city = address_data.get("city", "").strip()
        postal_code = address_data.get("postal_code", "").strip()

        if street or city or postal_code:
            norm_parsed_addr = normalize_string(parsed.address or "")
            norm_street = normalize_string(street)
            norm_city = normalize_string(city)
            norm_postcode = re.sub(r"\D", "", postal_code)
            norm_parsed_postcode = re.sub(r"\D", "", parsed.address or "")

            has_street = norm_street in norm_parsed_addr if norm_street else True
            has_city = norm_city in norm_parsed_addr if norm_city else True
            has_postcode = norm_postcode in norm_parsed_postcode if norm_postcode else True

            if not (has_street and has_city and has_postcode):
                warnings.append(
                    str(_("Agreement address does not match onboarding address: %(onboarding_addr)s.") % {
                        "onboarding_addr": f"{street}, {postal_code} {city}".strip(", "),
                    })
                )
        else:
            warnings.append(str(_("Address details are not filled in onboarding profile.")))
    else:
        warnings.append(str(_("Onboarding address data not found.")))

    # 3. Verify validity/expiry
    if parsed.valid_until:
        if parsed.valid_until < date.today():
            warnings.append(
                str(_("Rental agreement has expired on %(expiry)s.") % {"expiry": parsed.valid_until.isoformat()})
            )

    parsed_payload = {
        "address": parsed.address,
        "valid_until": parsed.valid_until.isoformat() if parsed.valid_until else None,
        "monthly_cost": parsed.monthly_cost,
        "detected_names": parsed.detected_names,
        "warnings": warnings,
        "has_name_mismatch": not name_matched,
    }

    return _finalize_successful_ocr_job(
        job_id=job.id,
        source_file_name=source_file_name,
        parsed_payload=parsed_payload,
        warnings=warnings,
        doc_type_display=str(_("Rental Agreement")),
    )


_ALLOWED_STANDARD_INSURANCE_PREFIXES = ("0110", "0411", "0412", "0444")


def _process_zus_doc_job_internal(
    job: DocumentProcessingJob,
    source_file_name: str,
    document_file: Any,
) -> DocumentProcessingRunResult:
    from clients.services.zus_parser import parse_zus_doc

    try:
        with document_file.open("rb") as src:
            ext = os.path.splitext(document_file.name or "")[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                for chunk in src.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
        try:
            parsed = parse_zus_doc(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as exc:
        logger.warning(
            "Automatic ZUS document parsing failed for queued job %s: error_type=%s",
            job.id,
            type(exc).__name__,
        )
        return _finalize_failed_ocr_job(
            job_id=job.id,
            source_file_name=source_file_name,
            error_message=str(_("Automatic ZUS document parsing failed.")),
        )

    if parsed.error == "no_text":
        return _finalize_failed_ocr_job(
            job_id=job.id,
            source_file_name=source_file_name,
            error_message=str(_("Could not extract any text from the ZUS document.")),
        )

    document = job.document
    client = document.client
    warnings: list[str] = []
    infos: list[str] = []

    # 1. Verify name.
    name_matched = _check_client_name_in_document(client, parsed.detected_names, parsed.text)
    if not name_matched:
        warnings.append(str(_("Client name not matched in the ZUS document.")))

    # 2. Verify / auto-fill ZUS RCA reporting month.
    is_registration_form = False
    form_type = getattr(parsed, "zus_form_type", None)
    if form_type in ("ZUA", "ZCNA", "ZZA", "ZWUA"):
        is_registration_form = True
    elif parsed.text:
        normalized_text = parsed.text.upper()
        if any(t in normalized_text for t in ("ZUS ZUA", "ZUS ZCNA", "ZUS ZZA", "ZUS ZWUA")):
            is_registration_form = True

    if is_registration_form:
        detected_month = None
        saved_month = None
        display_month = None
        month_mismatch = False
        if document.zus_period_month is not None:
            document.zus_period_month = None
            document.save(update_fields=["zus_period_month"])
    else:
        detected_month = getattr(parsed, "period_month", None)
        month_warnings, month_infos, month_mismatch, final_month = _build_zus_month_status(
            document,
            detected_month,
        )
        warnings.extend(month_warnings)
        infos.extend(month_infos)
        saved_month, assignment_message = _safe_assign_zus_month(document, final_month)
        if assignment_message:
            if saved_month == final_month:
                infos.append(assignment_message)
            else:
                warnings.append(assignment_message)

        display_month = saved_month or final_month or _normalize_month(document.zus_period_month)

    # 3. Verify employer NIP.
    contract_nip = None
    from clients.constants import COMPANY_DOCUMENT_TYPES
    company_docs = Document.objects.filter(
        client=client,
        document_type__in=list(COMPANY_DOCUMENT_TYPES),
        ocr_status__in=["success", "completed"],
    )
    for doc in company_docs:
        if doc.parsed_data and isinstance(doc.parsed_data, dict):
            nip_val = doc.parsed_data.get("nip")
            if nip_val:
                contract_nip = re.sub(r"[^\d]", "", str(nip_val))
                break

    if parsed.employer_nip:
        zus_nip_clean = re.sub(r"[^\d]", "", parsed.employer_nip)
        if contract_nip:
            if zus_nip_clean != contract_nip:
                warnings.append(
                    str(_("ZUS employer NIP (%(zus_nip)s) does not match contract NIP (%(contract_nip)s).") % {
                        "zus_nip": parsed.employer_nip,
                        "contract_nip": contract_nip,
                    })
                )
        else:
            from clients.services.company_parser import validate_nip

            if not validate_nip(zus_nip_clean):
                warnings.append(str(_("Extracted employer NIP %(nip)s is invalid.") % {"nip": parsed.employer_nip}))
    else:
        # ZCNA may not always contain employer NIP in a standard location
        if form_type != "ZCNA":
            warnings.append(str(_("Could not extract employer NIP from the ZUS document.")))

    # 4. Check insurance code. 0444 is a real code in this workflow, so do not warn.
    if form_type != "ZCNA":
        if parsed.insurance_code:
            if not parsed.insurance_code.startswith(_ALLOWED_STANDARD_INSURANCE_PREFIXES):
                warnings.append(
                    str(_("Insurance code '%(code)s' indicates non-standard employment type (expected Umowa o pracę/zlecenie).") % {
                        "code": parsed.insurance_code,
                    })
                )
            else:
                infos.append(
                    str(_("Insurance code %(code)s accepted.") % {"code": parsed.insurance_code})
                )
        else:
            warnings.append(str(_("Could not extract insurance code (e.g. 011000) from ZUS.")))

    # Build form-specific display name
    if form_type:
        doc_type_label = str(_("ZUS %(form_type)s")) % {"form_type": form_type}
    else:
        doc_type_label = str(_("ZUS Document"))

    parsed_payload = {
        "employer_nip": parsed.employer_nip,
        "insurance_code": parsed.insurance_code,
        "detected_names": parsed.detected_names,
        "zus_form_type": form_type,
        "period_month": detected_month.isoformat() if detected_month else None,
        "ocr_month": detected_month.isoformat() if detected_month else None,
        "ocr_month_display": _format_month(detected_month) if detected_month else "",
        "manual_month": saved_month.isoformat() if saved_month else None,
        "manual_month_display": _format_month(saved_month) if saved_month else "",
        "detected_month": display_month.isoformat() if display_month else None,
        "detected_month_display": _format_month(display_month) if display_month else "",
        "month_mismatch": month_mismatch,
        "warnings": warnings,
        "infos": infos,
        "has_name_mismatch": not name_matched,
    }

    return _finalize_successful_ocr_job(
        job_id=job.id,
        source_file_name=source_file_name,
        parsed_payload=parsed_payload,
        warnings=warnings,
        doc_type_display=doc_type_label,
    )


def _process_insurance_doc_job_internal(
    job: DocumentProcessingJob,
    source_file_name: str,
    document_file: Any,
) -> DocumentProcessingRunResult:
    from clients.services.insurance_parser import parse_insurance_doc

    try:
        with document_file.open("rb") as src:
            ext = os.path.splitext(document_file.name or "")[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                for chunk in src.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
        try:
            parsed = parse_insurance_doc(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as exc:
        logger.warning(
            "Automatic insurance parsing failed for queued job %s: error_type=%s",
            job.id,
            type(exc).__name__,
        )
        return _finalize_failed_ocr_job(
            job_id=job.id,
            source_file_name=source_file_name,
            error_message=str(_("Automatic insurance parsing failed.")),
        )

    if parsed.error == "no_text":
        return _finalize_failed_ocr_job(
            job_id=job.id,
            source_file_name=source_file_name,
            error_message=str(_("Could not extract any text from the insurance document.")),
        )

    # The "ZUS RCA or insurance" slot routes to the insurance parser whenever the
    # ZUS reporting month has not been selected manually. A ZUS RCA (or any other
    # ZUS form) uploaded without a month would otherwise be verified as a private
    # insurance policy and produce misleading "missing coverage/expiry" warnings.
    # Re-route to the ZUS parser when the OCR text clearly identifies a ZUS form.
    if job.document.document_type == DocumentType.ZUS_RCA_OR_INSURANCE.value:
        from clients.services.zus_parser import _detect_zus_form_type

        if _detect_zus_form_type(parsed.text):
            logger.info(
                "Re-routing ZUS_RCA_OR_INSURANCE job %s from insurance to ZUS parsing "
                "(detected ZUS form in OCR text).",
                job.id,
            )
            return _process_zus_doc_job_internal(job, source_file_name, document_file)

    client = job.document.client
    warnings = []

    # 1. Verify Name
    name_matched = _check_client_name_in_document(client, parsed.detected_names, parsed.text)
    if not name_matched:
        warnings.append(str(_("Client name not matched in the insurance policy.")))

    # 2. Verify validity/expiry
    if parsed.valid_until:
        if parsed.valid_until < date.today():
            warnings.append(
                str(_("Insurance policy has expired on %(expiry)s.") % {"expiry": parsed.valid_until.isoformat()})
            )
    else:
        warnings.append(str(_("Could not extract insurance expiration date.")))

    # 3. Verify Coverage Limit (>= 30,000 EUR or >= 120,000 PLN)
    if parsed.coverage_amount and parsed.currency:
        if parsed.currency == "EUR" and parsed.coverage_amount < 30000.0:
            warnings.append(
                str(_("Insurance coverage limit (%(amount)s EUR) is below the statutory minimum of 30,000 EUR.") % {
                    "amount": parsed.coverage_amount
                })
            )
        elif parsed.currency == "PLN" and parsed.coverage_amount < 120000.0:
            warnings.append(
                str(_("Insurance coverage limit (%(amount)s PLN) is below the statutory minimum of 120,000 PLN.") % {
                    "amount": parsed.coverage_amount
                })
            )
        elif parsed.currency not in ("EUR", "PLN"):
            warnings.append(
                str(_("Insurance coverage currency is '%(curr)s' (expected EUR or PLN). Cannot verify coverage limit.") % {
                    "curr": parsed.currency
                })
            )
    else:
        warnings.append(str(_("Could not extract insurance coverage amount or currency (min 30,000 EUR / 120,000 PLN).")))

    parsed_payload = {
        "valid_until": parsed.valid_until.isoformat() if parsed.valid_until else None,
        "coverage_amount": parsed.coverage_amount,
        "currency": parsed.currency,
        "detected_names": parsed.detected_names,
        "warnings": warnings,
        "has_name_mismatch": not name_matched,
    }

    return _finalize_successful_ocr_job(
        job_id=job.id,
        source_file_name=source_file_name,
        parsed_payload=parsed_payload,
        warnings=warnings,
        doc_type_display=str(_("Health Insurance")),
    )


def _save_client_document(
    *,
    client: Client,
    doc_type: str,
    uploaded_document: Document,
    actor: AbstractBaseUser | AnonymousUser | None,
    case: Case | None = None,
) -> Document:
    uploaded_document.client = client
    uploaded_document.document_type = doc_type
    if case is not None:
        uploaded_document.case = case
    # Inherit the data-classification flags from the client: a document uploaded
    # for a Test Center/Demo client via a view (staff UI or client portal) must
    # never be treated as production data; otherwise cleanup leaves it behind
    # (Case is PROTECT-referenced) and metrics count it as real.
    if client.is_test_data:
        uploaded_document.is_test_data = True
    if client.is_demo_data:
        uploaded_document.is_demo_data = True
    try:
        uploaded_document.save()
    except Exception:
        _cleanup_saved_document_files([uploaded_document])
        raise
    return uploaded_document


def _cleanup_saved_document_files(pending_documents: list[Document]) -> None:
    for pending_document in pending_documents:
        saved_file = getattr(pending_document, "file", None)
        if not saved_file or not getattr(saved_file, "_committed", False):
            continue

        file_name = getattr(saved_file, "name", "")
        if not file_name:
            continue

        try:
            if saved_file.storage.exists(file_name):
                saved_file.delete(save=False)
        except Exception:
            logger.warning(
                "Failed to clean up uploaded document file after save failure: document_id=%s",
                getattr(pending_document, "pk", None),
                exc_info=True,
            )


def _process_upload_job_inline(
    *,
    job_id: int,
    document: Document,
    document_type_display: str,
    parser: Parser,
    send_missing_email: NotificationSender,
    send_appointment_email: NotificationSender,
) -> DocumentUploadResult:
    result = process_document_processing_job(
        job_id=job_id,
        parser=parser,
        send_missing_email=send_missing_email,
        send_appointment_email=send_appointment_email,
    )
    document.refresh_from_db()

    if document.awaiting_confirmation:
        return DocumentUploadResult(
            document=document,
            message=_("Document uploaded. Review recognized data before applying it."),
            pending_confirmation=True,
            parsed_payload=document.parsed_data or {},
        )

    manual_review_required = result.manual_review_required or document.ocr_status == "failed"
    return DocumentUploadResult(
        document=document,
        message=_compose_upload_message(
            document_type_display=document_type_display,
            auto_updates=result.auto_updates,
            manual_review_required=manual_review_required,
        ),
        manual_review_required=manual_review_required,
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
            .select_related("document", "document__client")
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
            .select_related("document", "document__client")
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
        parsed_payload = _build_wezwanie_payload(parsed)

        if job.requires_confirmation:
            document.parsed_data = parsed_payload
            document.ocr_status = "success"
            document.awaiting_confirmation = True
            document.ocr_name_mismatch = _has_name_mismatch(parsed.full_name, client)
            document.save(update_fields=["parsed_data", "ocr_status", "awaiting_confirmation", "ocr_name_mismatch"])
        else:
            case = document.case if document.case_id else None
            case_fields, client_fields, parsed_updates = _apply_parsed_client_updates(
                case,
                client,
                parsed,
                actor=actor,
            )
            auto_updates.extend(parsed_updates)
            _append_required_documents_update(parsed, auto_updates)

            if case is not None and case_fields:
                case.save(update_fields=case_fields)
                log_client_activity(
                    client=client,
                    case=case,
                    actor=actor,
                    event_type="case_updated",
                    summary="Дело обновлено",
                    metadata={"case_id": str(case.uuid), "changed_fields": case_fields},
                    document=document,
                )
            if client_fields:
                client.save(update_fields=client_fields)
                log_client_activity(
                    client=client,
                    case=case,
                    actor=actor,
                    event_type="client_updated",
                    summary="Client name updated from background wezwanie OCR",
                    metadata={"changed_fields": client_fields},
                    document=document,
                )

            document.parsed_data = parsed_payload
            document.ocr_status = "success"
            document.awaiting_confirmation = False
            document.ocr_name_mismatch = _has_name_mismatch(parsed.full_name, client)
            document.scrub_parsed_pii()
            document.save(update_fields=["parsed_data", "ocr_status", "awaiting_confirmation", "ocr_name_mismatch"])

        requires_confirmation = job.requires_confirmation
        job.status = DocumentProcessingJob.STATUS_COMPLETED
        job.error_message = ""
        job.completed_at = timezone.now()
        job.lease_expires_at = None
        job.next_attempt_at = None
        job.save(update_fields=["status", "error_message", "completed_at", "lease_expires_at", "next_attempt_at"])

    if not requires_confirmation:
        auto_updates.extend(
            _send_background_notifications(
                client=client,
                case=job.case,
                parsed=parsed,
                send_missing_email=send_missing_email,
                send_appointment_email=send_appointment_email,
            )
        )

    return DocumentProcessingRunResult(
        job=job,
        status=DocumentProcessingJob.STATUS_COMPLETED,
        processed=True,
        message=_(
            "Queued OCR job completed and awaits confirmation."
            if requires_confirmation
            else "Queued OCR job completed successfully."
        ),
        auto_updates=auto_updates,
    )


def _job_matches_processing_state(
    job: DocumentProcessingJob,
    document: Document,
    source_file_name: str,
) -> bool:
    current_file_identity = _document_file_identity(document)
    return (
        job.status == DocumentProcessingJob.STATUS_PROCESSING
        and job.source_file_name == source_file_name
        and source_file_name in {current_file_identity, document.file.name or ""}
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


def _send_background_notifications(
    *,
    client: Client,
    case: Case | None,
    parsed: WezwanieData,
    send_missing_email: NotificationSender,
    send_appointment_email: NotificationSender,
) -> list[str]:
    auto_updates: list[str] = []

    if _send_notification(send_missing_email, client, "missing-documents email", case=case):
        auto_updates.append(_("missing-documents email sent"))

    if parsed.wezwanie_type == "fingerprints" and parsed.fingerprints_date:
        if _send_notification(send_appointment_email, client, "appointment notification", case=case):
            auto_updates.append(_("appointment notification sent"))

    return auto_updates


def _send_notification(sender: NotificationSender, client: Client, label: str, *, case: Case | None = None) -> bool:
    try:
        if case is not None:
            try:
                return bool(sender(client, case=case))
            except TypeError as exc:
                if "case" not in str(exc):
                    raise
        return bool(sender(client))
    except Exception as exc:
        logger.warning(
            "Failed to send %s for client_id=%s error_type=%s",
            label,
            client.pk,
            type(exc).__name__,
        )
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
