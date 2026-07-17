from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext as _

from clients.constants import DocumentType
from clients.models import Case, Client, Document, DocumentProcessingJob
from clients.security.encrypted import read_encrypted_json_dict, require_encrypted_json_dict
from clients.services.activity import log_client_activity
from clients.services.document_workflow_wezwanie import (
    _apply_confirmation_updates,
    _build_confirmed_wezwanie_notification_data,
    _build_confirmed_wezwanie_payload,
)
from clients.services.notifications import (
    send_appointment_notification_email,
    send_missing_documents_email,
)
from clients.services.wezwanie_parser import parse_wezwanie

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

# --- split modules ------------------------------------------------------------
# The queue infrastructure, per-type processors and shared result types were
# extracted into sibling modules; re-export them so existing imports and test
# patch targets keep working.
from clients.services.document_job_processors import (  # noqa: F401
    _check_client_name_in_document,
    _compose_upload_message,
    _finalize_failed_company_job,
    _finalize_failed_document_job,
    _finalize_failed_ocr_job,
    _finalize_successful_company_job,
    _finalize_successful_document_job,
    _finalize_successful_ocr_job,
    _process_company_doc_job_internal,
    _process_insurance_doc_job_internal,
    _process_passport_doc_job_internal,
    _process_rental_doc_job_internal,
    _process_zus_doc_job_internal,
    _send_background_notifications,
    _send_notification,
)
from clients.services.document_jobs import (  # noqa: F401
    enqueue_document_processing_job,
    process_document_processing_job,
    process_pending_document_jobs,
    reclaim_stale_document_jobs,
)
from clients.services.document_processing_common import (  # noqa: F401
    DEFAULT_JOB_LEASE_SECONDS,
    DEFAULT_JOB_MAX_ATTEMPTS,
    MANUAL_WEZWANIE_REVIEW_MESSAGE,
    DocumentProcessingRunResult,
    DocumentUploadResult,
    NotificationSender,
    Parser,
    WezwanieConfirmationResult,
    _document_file_identity,
    _job_matches_processing_state,
)

logger = logging.getLogger(__name__)


def _document_parsed_payload(document: Document) -> tuple[dict[str, Any], bool]:
    return read_encrypted_json_dict(document, "parsed_data")


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

        # Heavy OCR (tesseract over multi-page PDFs) must not hold a web worker
        # hostage on every routine upload. Auto-recognition job types therefore
        # default to the queue (ASYNC_AUTO_OCR_PROCESSING) and are picked up by
        # the automation loop / cron webhook. The interactive wezwanie parse is
        # the exception: staff explicitly clicked "recognize" and the modal
        # shows the parsed fields inline, so it stays synchronous unless the
        # global ASYNC_OCR_PROCESSING override queues everything.
        force_async = getattr(settings, "ASYNC_OCR_PROCESSING", False)
        auto_async = getattr(settings, "ASYNC_AUTO_OCR_PROCESSING", False)
        queue_job = force_async or (auto_async and not requires_confirmation)

        if not queue_job:
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

    require_encrypted_json_dict(document, "parsed_data")

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


def _process_company_upload_job_inline(
    *,
    job_id: int,
    document: Document,
    document_type_display: str,
) -> DocumentUploadResult:
    result = process_document_processing_job(job_id=job_id)
    document.refresh_from_db()

    parsed_payload, encrypted_data_unavailable = _document_parsed_payload(document)
    manual_review_required = (
        result.manual_review_required or document.ocr_status == "failed" or encrypted_data_unavailable
    )
    return DocumentUploadResult(
        document=document,
        message=_("Document '%(name)s' uploaded and verified: %(msg)s") % {
            "name": document_type_display,
            "msg": result.message,
        },
        manual_review_required=manual_review_required,
        parsed_payload=parsed_payload,
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
        parsed_payload, encrypted_data_unavailable = _document_parsed_payload(document)
        if encrypted_data_unavailable:
            return DocumentUploadResult(
                document=document,
                message=_(
                    "Recognized document data is temporarily unavailable. "
                    "Restore the encryption key before confirming it."
                ),
                manual_review_required=True,
                pending_confirmation=False,
                parsed_payload={},
            )
        return DocumentUploadResult(
            document=document,
            message=_("Document uploaded. Review recognized data before applying it."),
            pending_confirmation=True,
            parsed_payload=parsed_payload,
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
