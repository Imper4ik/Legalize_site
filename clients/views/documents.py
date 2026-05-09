from __future__ import annotations

import logging
from pathlib import Path
from typing import cast, TYPE_CHECKING

from django.contrib import messages
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext as _

from clients.constants import DocumentType, is_wezwanie_document_type
from clients.forms import DocumentUploadForm
from clients.models import Client, Document, WniosekAttachment
from clients.services.access import (
    accessible_clients_queryset,
    accessible_documents_queryset,
    user_has_internal_role,
)
from clients.services.document_helpers import document_file_exists
from clients.services.document_workflow import confirm_wezwanie_document, upload_client_document
from clients.services.notifications import (
    send_appointment_notification_email,
    send_missing_documents_email,
)
from clients.services.permissions import has_employee_permission
from clients.services.responses import ResponseHelper, apply_no_store
from clients.services.roles import DOCUMENT_DELETE_ROLES, DOCUMENT_EDIT_ROLES
from clients.services.wezwanie_parser import parse_wezwanie
from clients.use_cases.documents import (
    delete_client_document,
    delete_wniosek_attachment,
    record_document_download,
    toggle_client_document_verification,
    update_client_notes_for_client,
    verify_all_client_documents,
)
from clients.views.base import role_or_feature_required_view, role_required_view, staff_required_view
from legalize_site.utils.files import build_protected_file_response

if TYPE_CHECKING:
    from django.http.response import HttpResponseBase
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

logger = logging.getLogger(__name__)


def _can_run_ocr_review(user: AbstractBaseUser | AnonymousUser | None) -> bool:
    return (
        user_has_internal_role(user, "Admin", "Manager")
        or has_employee_permission(user, "can_run_ocr_review")
    )


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

        files = request.FILES.getlist('file')
        if not files:
            form = DocumentUploadForm(request.POST, request.FILES, doc_type=doc_type, client=client)
            if helper.expects_json:
                return helper.error(
                    message=str(_("Проверьте правильность заполнения формы.")),
                    errors=form.errors.get_json_data(),
            )
            return redirect("clients:client_detail", pk=client.id)

        if doc_type == DocumentType.ZUS_RCA_OR_INSURANCE.value and len(files) > 1:
            message = _("ZUS RCA can be uploaded only one month at a time.")
            if helper.expects_json:
                return helper.error(message=str(message), errors={"file": [{"message": str(message)}]})
            messages.error(request, message)
            return redirect("clients:client_detail", pk=client.id)

        upload_results = []
        success_count = 0
        errors = {}

        for f in files:
            file_dict = {'file': f}
            form = DocumentUploadForm(request.POST, file_dict, doc_type=doc_type, client=client)
            if form.is_valid():
                result = upload_client_document(
                    client=client,
                    doc_type=doc_type,
                    uploaded_document=form.save(commit=False),
                    actor=request.user,
                    parse_requested=parse_requested,
                    parser=parse_wezwanie,
                    send_missing_email=send_missing_documents_email,
                    send_appointment_email=send_appointment_notification_email,
                )
                upload_results.append(result)
                success_count += 1
            else:
                errors = form.errors.get_json_data()
                break

        if success_count > 0 and success_count == len(files):
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


@role_or_feature_required_view("can_run_ocr_review", "Admin", "Manager")
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

    result = confirm_wezwanie_document(
        document=document,
        actor=request.user,
        confirmation_data=request.POST,
        parser=parse_wezwanie,
        send_missing_email=send_missing_documents_email,
        send_appointment_email=send_appointment_notification_email,
    )

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

    return redirect("clients:client_detail", pk=client_id)


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
    return redirect("clients:client_detail", pk=document.client.id)


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
            verified_count=result.updated_count,
            emails_sent=result.emails_sent,
        )

    if result.updated_count:
        message = _("Отмечено %(count)s документов как проверенные.") % {"count": result.updated_count}
        if result.emails_sent:
            message += " " + _("Письмо с недостающими документами отправлено.")
        messages.success(request, message)
    else:
        messages.info(request, _("Все загруженные документы уже проверены."))

    return redirect("clients:client_detail", pk=client.id)


def _serve_document_file(request: HttpRequest, doc_id: int, *, as_attachment: bool) -> HttpResponseBase:
    action = "download" if as_attachment else "preview"
    logger.info("Document %s requested: doc_id=%s, user_id=%s", action, doc_id, getattr(request.user, 'pk', 'None'))
    
    document = get_object_or_404(
        accessible_documents_queryset(request.user, Document.objects.select_related("client")),
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
    checklist_html = render_to_string(
        "clients/partials/document_checklist.html",
        {
            "document_status_list": client.get_document_checklist(check_file_existence=True),
            "client": client,
        },
    )
    helper = ResponseHelper(request)
    return helper.success(checklist_html=checklist_html)


@staff_required_view
def client_overview_partial(request: HttpRequest, pk: int) -> HttpResponseBase:
    """Return the rendered client overview partial for AJAX refreshes."""

    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=pk)
    document_status_list = client.get_document_checklist(check_file_existence=True)
    overview_html = render_to_string(
        "clients/partials/client_overview.html",
        {
            "client": client,
            "workflow_summary": client.get_workflow_summary(document_status_list=document_status_list),
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
    document_status_list = client.get_document_checklist(check_file_existence=True)
    response = render(
        request,
        "clients/partials/document_checklist.html",
        {
            "client": client,
            "document_status_list": document_status_list,
        },
    )
    return apply_no_store(response)


@role_or_feature_required_view("can_run_ocr_review", "Admin", "Manager")
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

    return JsonResponse({"parsed_data": document.parsed_data or {}})
