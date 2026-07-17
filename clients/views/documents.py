from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext as _

from clients.constants import DocumentType, is_wezwanie_document_type
from clients.forms import ClientDocumentRequirementForm, DocumentUploadForm
from clients.models import Client, ClientDocumentRequirement, Document, WniosekAttachment
from clients.security.encrypted import (
    EncryptedFieldUnavailableError,
    read_encrypted_json_dict,
    safe_encrypted_attr,
)
from clients.services.access import (
    accessible_clients_queryset,
    accessible_documents_queryset,
)
from clients.services.cases import resolve_single_active_case
from clients.services.custom_document_requirements import sync_custom_document_requirement_reminder
from clients.services.document_helpers import document_file_exists
from clients.services.document_workflow import confirm_wezwanie_document, upload_client_document
from clients.services.notifications import (
    send_appointment_notification_email,
    send_missing_documents_email,
)
from clients.services.permissions import user_can_run_ocr_review
from clients.services.responses import ResponseHelper, apply_no_store
from clients.services.roles import DOCUMENT_DELETE_ROLES, DOCUMENT_EDIT_ROLES, OCR_REVIEW_ALLOWED_ROLES
from clients.services.wezwanie_parser import parse_wezwanie
from clients.services.zus import missing_zus_month_upload_options
from clients.use_cases.documents import (
    delete_client_document,
    delete_wniosek_attachment,
    record_document_download,
    toggle_client_document_verification,
    update_client_notes_for_client,
    verify_all_client_documents,
)
from clients.views.base import (
    role_or_feature_required_view,
    role_required_view,
    safe_redirect_target,
    staff_required_view,
)
from legalize_site.utils.files import build_protected_file_response

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
    from django.http.response import HttpResponseBase

logger = logging.getLogger(__name__)


def _uploaded_file_log_payload(files: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "size": getattr(uploaded_file, "size", None),
            "content_type": getattr(uploaded_file, "content_type", ""),
        }
        for uploaded_file in files
    ]


def _can_run_ocr_review(user: AbstractBaseUser | AnonymousUser | None) -> bool:
    return user_can_run_ocr_review(user)


@role_required_view(*DOCUMENT_EDIT_ROLES)
def update_client_notes(request: HttpRequest, pk: int) -> HttpResponseBase:
    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=pk)
    helper = ResponseHelper(request)

    if request.method == "POST":
        update_client_notes_for_client(
            client=client,
            actor=request.user,
            notes=request.POST.get("notes", ""),
        )
        if helper.expects_json:
            return helper.success(message=str(_("Заметка сохранена")))
        messages.success(request, _("Заметка сохранена."))
        return redirect("clients:client_detail", pk=pk)
    return redirect("clients:client_list")


@role_required_view(*DOCUMENT_EDIT_ROLES)
def add_document(request: HttpRequest, client_id: int, doc_type: str) -> HttpResponseBase:
    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=client_id)
    document_type_display = client.get_document_name_by_code(doc_type)
    helper = ResponseHelper(request)

    if request.method == "POST":
        parse_requested = request.POST.get("parse_wezwanie") == "1"
        if parse_requested and not _can_run_ocr_review(request.user):
            return helper.forbidden()

        # Uploads are stored against a concrete case (spec §1/§5, shim-exit):
        # an explicit case_uuid wins; otherwise the client's single active case
        # is used. With several active cases and no explicit choice the upload
        # is refused with a message instead of the model-level legacy fallback
        # raising an unhandled ValidationError (HTTP 500).
        from clients.services.cases import resolve_active_case_for_client

        case_uuid = request.POST.get("case_uuid")
        case = resolve_active_case_for_client(client, case_uuid) if case_uuid else resolve_single_active_case(client)
        if case is None:
            message = _("Для этой операции необходимо выбрать дело.")
            if case_uuid:
                message = _("Дело не найдено.")
            if helper.expects_json:
                return helper.error(message=str(message))
            messages.error(request, message)
            return redirect("clients:client_detail", pk=client.id)

        files = request.FILES.getlist('file')
        if not files:
            form = DocumentUploadForm(request.POST, request.FILES, doc_type=doc_type, client=client, case=case)
            errors = form.errors.get_json_data()
            logger.warning(
                "Document upload rejected: client_id=%s doc_type=%s errors=%s files=%s",
                client.pk,
                doc_type,
                errors,
                _uploaded_file_log_payload(files),
            )
            if helper.expects_json:
                return helper.error(
                    message=str(_("Проверьте правильность заполнения формы.")),
                    errors=errors,
            )
            return redirect("clients:client_detail", pk=client.id)

        if doc_type == DocumentType.ZUS_RCA_OR_INSURANCE.value and len(files) > 1:
            message = _("ZUS RCA can be uploaded only one month at a time.")
            logger.warning(
                "Document upload rejected: client_id=%s doc_type=%s reason=multiple_zus_files files=%s",
                client.pk,
                doc_type,
                _uploaded_file_log_payload(files),
            )
            if helper.expects_json:
                return helper.error(message=str(message), errors={"file": [{"message": str(message)}]})
            messages.error(request, message)
            return redirect("clients:client_detail", pk=client.id)

        # Validate every file before persisting any of them. Previously a bad
        # file mid-batch broke the loop after earlier files were already saved,
        # leaving a partial, non-atomic upload. Validate first, then persist the
        # whole batch inside a single transaction so it is all-or-nothing.
        validated_forms = []
        errors = {}
        for f in files:
            form = DocumentUploadForm(request.POST, {'file': f}, doc_type=doc_type, client=client, case=case)
            if not form.is_valid():
                errors = form.errors.get_json_data()
                logger.warning(
                    "Document upload rejected: client_id=%s doc_type=%s errors=%s files=%s",
                    client.pk,
                    doc_type,
                    errors,
                    _uploaded_file_log_payload([f]),
                )
                break
            validated_forms.append(form)

        upload_results = []
        success_count = 0
        if not errors and validated_forms:
            # A DB rollback does not remove files already written to storage
            # (django-cleanup only fires on model delete). Keep a reference to
            # every Document instance passed into the workflow *before* the call,
            # because upload_client_document writes the physical file during
            # document.save() and may then raise (auto-task, activity log, OCR
            # enqueue) before returning. On failure we delete the file of any of
            # those documents that actually reached storage, so a failed batch
            # leaves neither DB rows nor orphaned media.
            pending_documents: list[Document] = []
            try:
                with transaction.atomic():
                    for form in validated_forms:
                        pending_document = form.save(commit=False)
                        pending_documents.append(pending_document)
                        result = upload_client_document(
                            client=client,
                            doc_type=doc_type,
                            uploaded_document=pending_document,
                            actor=request.user,
                            case=case,
                            parse_requested=parse_requested,
                            parser=parse_wezwanie,
                            send_missing_email=send_missing_documents_email,
                            send_appointment_email=send_appointment_notification_email,
                        )
                        upload_results.append(result)
                        success_count += 1
            except Exception:
                for pending_document in pending_documents:
                    saved_file = getattr(pending_document, "file", None)
                    if not saved_file:
                        continue
                    name = getattr(saved_file, "name", "")
                    if not name:
                        continue
                    try:
                        if saved_file.storage.exists(name):
                            saved_file.storage.delete(name)
                    except Exception:  # pragma: no cover - best-effort cleanup
                        logger.warning(
                            "Failed to remove orphaned upload after rollback: client_id=%s name=%s",
                            client.pk,
                            name,
                        )
                raise

        if success_count > 0 and success_count == len(files):
            custom_requirement = ClientDocumentRequirement.objects.filter(
                client=client,
                document_type=doc_type,
                is_active=True,
            ).first()
            if custom_requirement:
                sync_custom_document_requirement_reminder(custom_requirement)
            last_result = upload_results[-1]
            if helper.expects_json:
                primary_result = next(
                    (item for item in upload_results if item.pending_confirmation),
                    last_result,
                )
                documents_payload = [
                    {
                        "doc_id": item.document.id,
                        "manual_review_required": item.manual_review_required,
                        "pending_confirmation": item.pending_confirmation,
                        "ocr_processing_queued": item.ocr_processing_queued,
                        "parsed": item.parsed_payload,
                    }
                    for item in upload_results
                ]

                msg = str(_("Загружено документов: %(count)s") % {"count": success_count}) if success_count > 1 else last_result.message

                return helper.success(
                    message=msg,
                    doc_id=primary_result.document.id,
                    manual_review_required=primary_result.manual_review_required,
                    pending_confirmation=primary_result.pending_confirmation,
                    ocr_processing_queued=primary_result.ocr_processing_queued,
                    parsed=primary_result.parsed_payload,
                    documents=documents_payload,
                )

            if last_result.manual_review_required:
                messages.warning(request, last_result.message)
            else:
                msg = _("Загружено документов: %(count)s") % {"count": success_count} if success_count > 1 else last_result.message
                messages.success(request, msg)
            return redirect("clients:client_detail", pk=client.id)

        if helper.expects_json:
            return helper.error(
                message=str(_("Проверьте правильность заполнения формы.")),
                errors=errors,
            )

    form = DocumentUploadForm(doc_type=doc_type, client=client)
    return render(
        request,
        "clients/add_document.html",
        {
            "form": form,
            "client": client,
            "doc_type": doc_type,
            "document_type_display": document_type_display,
        },
    )


@role_required_view(*DOCUMENT_EDIT_ROLES)
def add_client_document_requirement(request: HttpRequest, client_id: int) -> HttpResponseBase:
    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=client_id)
    if request.method == "POST":
        form = ClientDocumentRequirementForm(request.POST, client=client)
        if form.is_valid():
            requirement = form.save(commit=False)
            requirement.client = client
            requirement.created_by = request.user
            requirement.save()
            sync_custom_document_requirement_reminder(requirement)
            messages.success(request, _("Индивидуальный документ добавлен."))
    return redirect("clients:client_detail", pk=client.pk)


@role_or_feature_required_view("can_run_ocr_review", *OCR_REVIEW_ALLOWED_ROLES)
def confirm_wezwanie_parse(request: HttpRequest, doc_id: int) -> HttpResponseBase:
    document = get_object_or_404(accessible_documents_queryset(request.user, Document.objects.all()), pk=doc_id)
    helper = ResponseHelper(request)

    if request.method != "POST":
        if helper.expects_json:
            return helper.error(message=str(_("Недопустимый метод запроса.")), status=405)
        return redirect("clients:client_detail", pk=document.client.id)

    if not is_wezwanie_document_type(document.document_type):
        if helper.expects_json:
            return helper.error(message=str(_("Документ не является wezwanie.")), status=400)
        messages.error(request, _("Документ не является wezwanie."))
        return redirect("clients:client_detail", pk=document.client.id)

    try:
        result = confirm_wezwanie_document(
            document=document,
            actor=request.user,
            confirmation_data=request.POST,
            parser=parse_wezwanie,
            send_missing_email=send_missing_documents_email,
            send_appointment_email=send_appointment_notification_email,
        )
    except EncryptedFieldUnavailableError:
        message = _(
            "Recognized document data is temporarily unavailable. "
            "Restore the encryption key before confirming this document."
        )
        if helper.expects_json:
            return helper.error(message=str(message), status=409)
        messages.error(request, message)
        return redirect("clients:client_detail", pk=document.client.id)

    if helper.expects_json:
        return helper.success(
            message=result.message,
            manual_review_required=result.manual_review_required,
        )

    if result.manual_review_required:
        messages.warning(request, result.message)
    else:
        messages.success(request, result.message)
    return redirect("clients:client_detail", pk=document.client.id)


@role_or_feature_required_view("can_delete_documents", *DOCUMENT_DELETE_ROLES)
def document_delete(request: HttpRequest, pk: int) -> HttpResponseBase:
    document = get_object_or_404(accessible_documents_queryset(request.user, Document.objects.all()), pk=pk)
    client_id = document.client.id
    helper = ResponseHelper(request)

    if request.method == "POST":
        result = delete_client_document(document=document, actor=request.user)
        msg = str(_("Документ '%(name)s' удалён.") % {"name": result.document_display_name})
        if helper.expects_json:
            return helper.success(message=msg)

        messages.success(request, _("Документ '%(name)s' успешно удалён.") % {"name": result.document_display_name})
    else:
        messages.warning(request, _("Удаление возможно только через кнопку."))

    return redirect(
        safe_redirect_target(request) or reverse("clients:client_detail", kwargs={"pk": client_id})
    )


@role_or_feature_required_view("can_delete_documents", *DOCUMENT_DELETE_ROLES)
def wniosek_attachment_delete(request: HttpRequest, attachment_id: int) -> HttpResponseBase:
    attachment = get_object_or_404(
        WniosekAttachment.objects.select_related("submission", "submission__client").filter(
            submission__client__in=accessible_clients_queryset(request.user, Client.objects.all())
        ),
        pk=attachment_id,
    )
    submission = attachment.submission
    client_id = submission.client_id
    helper = ResponseHelper(request)

    if request.method == "POST":
        result = delete_wniosek_attachment(attachment=attachment, actor=request.user)
        message = str(_("Отметка '%(name)s' удалена.") % {"name": result.attachment_name})
        if helper.expects_json:
            return helper.success(message=message)

        messages.success(request, message)
    else:
        messages.warning(request, _("Удаление возможно только через кнопку."))

    return redirect("clients:client_detail", pk=client_id)


@role_required_view(*DOCUMENT_EDIT_ROLES)
def toggle_document_verification(request: HttpRequest, doc_id: int) -> HttpResponseBase:
    """Toggle verification status for a client document."""

    document = get_object_or_404(accessible_documents_queryset(request.user, Document.objects.all()), pk=doc_id)
    helper = ResponseHelper(request)
    if request.method == "POST":
        result = toggle_client_document_verification(
            document=document,
            actor=request.user,
            send_missing_email=send_missing_documents_email,
        )

        if helper.expects_json:
            return helper.success(
                verified=result.verified,
                button_text=str(_("Снять отметку") if result.verified else _("Проверить")),
                emails_sent=result.emails_sent,
            )

        status = _("проверен") if result.verified else _("не проверен")
        message_suffix = _(" Письмо с недостающими документами отправлено.") if result.emails_sent else ""
        messages.success(
            request,
            _("Статус изменен: %(status)s.") % {"status": status} + str(message_suffix),
        )
    return redirect(
        safe_redirect_target(request) or reverse("clients:client_detail", kwargs={"pk": document.client.id})
    )


@role_required_view(*DOCUMENT_EDIT_ROLES)
def verify_all_documents(request: HttpRequest, client_id: int) -> HttpResponseBase:
    """Mark all uploaded documents for the client as verified."""

    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=client_id)
    helper = ResponseHelper(request)

    if request.method != "POST":
        return redirect("clients:client_detail", pk=client.id)

    result = verify_all_client_documents(
        client=client,
        actor=request.user,
        send_missing_email=send_missing_documents_email,
    )

    if helper.expects_json:
        return helper.success(
            message=str(
                _("Подтверждено %(count)s документов, ожидающих проверки.") % {"count": result.updated_count}
                if result.updated_count
                else _("Все активные документы уже были проверены.")
            ),
            verified_count=result.updated_count,
            emails_sent=result.emails_sent,
        )

    if result.updated_count:
        message = _("Подтверждено %(count)s документов, ожидающих проверки.") % {"count": result.updated_count}
        if result.emails_sent:
            message += " " + _("Письмо с недостающими документами отправлено.")
        messages.success(request, message)
    else:
        messages.info(request, _("Все активные документы уже были проверены."))

    return redirect("clients:client_detail", pk=client.id)


def _serve_document_file(request: HttpRequest, doc_id: int, *, as_attachment: bool) -> HttpResponseBase:
    action = "download" if as_attachment else "preview"
    logger.info("Document %s requested: doc_id=%s, user_id=%s", action, doc_id, getattr(request.user, 'pk', 'None'))

    # Serve archived documents too: the case detail page lists documents of
    # archived cases (Document.all_objects) with preview/download buttons, and
    # staff must be able to open a file to decide about restoring it. Access is
    # still scoped by accessible_documents_queryset and every download is
    # logged via record_document_download.
    document = get_object_or_404(
        accessible_documents_queryset(
            request.user,
            Document.all_objects.select_related("client"),
            include_archived_cases=True,
        ),
        pk=doc_id,
    )

    if not document_file_exists(document):
        logger.warning(
            "Physical file missing in storage: document_id=%s, client_id=%s",
            document.pk,
            document.client_id,
        )
        messages.error(
            request,
            _("Файл отсутствует в хранилище. Загрузите файл заново."),
        )
        return cast('HttpResponseBase', redirect("clients:client_detail", pk=document.client.id))

    record_document_download(document=document, actor=request.user)
    file_name = str(document.file.name)
    extension = Path(file_name).suffix or ".bin"
    filename = f"document-{document.pk}{extension}"
    return build_protected_file_response(document.file, filename=filename, as_attachment=as_attachment)


@staff_required_view
def document_preview(request: HttpRequest, doc_id: int) -> HttpResponseBase:
    return _serve_document_file(request, doc_id, as_attachment=False)


@staff_required_view
def document_download(request: HttpRequest, doc_id: int) -> HttpResponseBase:
    return _serve_document_file(request, doc_id, as_attachment=True)


@staff_required_view
def client_status_api(request: HttpRequest, pk: int) -> HttpResponseBase:
    """Return the latest client checklist as JSON for AJAX refreshes."""

    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=pk)
    active_case = resolve_single_active_case(client)
    checklist_html = render_to_string(
        "clients/partials/document_checklist.html",
        {
            "document_status_list": client.get_document_checklist(check_file_existence=True),
            "missing_zus_months_for_upload": (missing_zus_month_upload_options(active_case) if active_case else []),
            "client": client,
        },
        request=request,
    )
    helper = ResponseHelper(request)
    return helper.success(checklist_html=checklist_html)


@staff_required_view
def client_overview_partial(request: HttpRequest, pk: int) -> HttpResponseBase:
    """Return the rendered client overview partial for AJAX refreshes."""

    client = get_object_or_404(
        accessible_clients_queryset(request.user, Client.objects.prefetch_related("mos_applications")),
        pk=pk,
    )
    document_status_list = client.get_document_checklist(check_file_existence=True)
    active_case = resolve_single_active_case(client)
    active_case_number = (
        safe_encrypted_attr(active_case, "authority_case_number", default="")
        if active_case is not None
        else ""
    )
    overview_html = render_to_string(
        "clients/partials/client_overview.html",
        {
            "client": client,
            "workflow_summary": client.get_workflow_summary(document_status_list=document_status_list),
            "active_case_number": active_case_number,
            "safe_case_number": active_case_number or _("Не указан"),
            "show_family_dashboard_link": bool(
                client.family_role
                or client.sponsor_client_id
                or client.application_purpose in {"family", "family_spouse", "family_child"}
                or client.sponsored_family_members.exists()
            ),
            "family_dashboard_url": reverse("clients:family_dashboard", kwargs={"pk": client.pk}),
        },
        request=request,
    )
    helper = ResponseHelper(request)
    return helper.success(html=overview_html)


@staff_required_view
def client_checklist_partial(request: HttpRequest, pk: int) -> HttpResponseBase:
    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=pk)
    active_case = resolve_single_active_case(client)

    active_cases_count = client.cases.filter(archived_at__isnull=True).count()
    if active_cases_count > 1:
        document_status_list: list[Any] = []
        has_multiple_active_cases = True
    else:
        document_status_list = client.get_document_checklist(check_file_existence=True, case=active_case)
        has_multiple_active_cases = False

    response = render(
        request,
        "clients/partials/document_checklist.html",
        {
            "client": client,
            "document_status_list": document_status_list,
            "has_multiple_active_cases": has_multiple_active_cases,
            "missing_zus_months_for_upload": (missing_zus_month_upload_options(active_case) if active_case else []),
        },
    )
    return apply_no_store(response)


@role_or_feature_required_view("can_run_ocr_review", *OCR_REVIEW_ALLOWED_ROLES)
def get_document_parsed_data(request: HttpRequest, doc_id: int) -> HttpResponseBase:
    document = (
        Document.objects.select_related("client")
        .filter(
            pk=doc_id,
            client__in=accessible_clients_queryset(request.user, Client.objects.all()),
        )
        .first()
    )
    if document is None:
        return JsonResponse({"error": str(_("Document not found."))}, status=404)
    if not document.awaiting_confirmation:
        return JsonResponse({"error": str(_("Document is not awaiting confirmation."))}, status=400)

    payload, encrypted_data_unavailable = read_encrypted_json_dict(document, "parsed_data")
    if encrypted_data_unavailable:
        return apply_no_store(
            JsonResponse(
                {"error": str(_("Recognized document data is temporarily unavailable."))},
                status=409,
            )
        )

    return apply_no_store(JsonResponse({"parsed_data": payload}))


@role_required_view(*DOCUMENT_EDIT_ROLES)
def reject_document(request: HttpRequest, doc_id: int) -> HttpResponseBase:
    """Set document status as rejected and specify the reason."""
    document = get_object_or_404(accessible_documents_queryset(request.user, Document.objects.all()), pk=doc_id)
    helper = ResponseHelper(request)
    if request.method == "POST":
        rejection_reason = request.POST.get("rejection_reason", "").strip()
        if rejection_reason:
            document.verified = False
            document.awaiting_confirmation = False
            document.rejection_reason = rejection_reason
            document.save(update_fields=["verified", "awaiting_confirmation", "rejection_reason"])

            from clients.services.activity import log_client_activity
            log_client_activity(
                client=document.client,
                actor=request.user,
                event_type="document_verified",
                summary="Документ отклонён",
                details="",
                metadata={"document_id": document.id},
                document=document,
            )

            from clients.services.tasks import close_auto_task
            close_auto_task(document.client, "document_review", document=document)

            if helper.expects_json:
                return helper.success(
                    message=str(_("Документ успешно отклонён.")),
                )
            messages.success(request, _("Документ отклонён."))
        else:
            if helper.expects_json:
                return helper.error(message=str(_("Укажите причину отклонения.")))
            messages.error(request, _("Укажите причину отклонения."))

    return redirect("clients:client_detail", pk=document.client.id)
