from __future__ import annotations

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext as _

from clients.constants import DocumentType
from clients.forms import DocumentUploadForm
from clients.models import Client, Document, WniosekAttachment
from clients.services.document_workflow import confirm_wezwanie_document, upload_client_document
from clients.services.notifications import (
    send_appointment_notification_email,
    send_missing_documents_email,
)
from clients.services.responses import ResponseHelper, apply_no_store
from clients.services.wezwanie_parser import parse_wezwanie
from clients.use_cases.documents import (
    delete_client_document,
    delete_wniosek_attachment,
    record_document_download,
    toggle_client_document_verification,
    update_client_notes_for_client,
    verify_all_client_documents,
)
from clients.services.access import accessible_clients_queryset, accessible_documents_queryset
from clients.services.roles import DOCUMENT_MUTATION_ROLES
from clients.views.base import role_required_view, staff_required_view
from legalize_site.utils.files import build_protected_file_response


@role_required_view(*DOCUMENT_MUTATION_ROLES)
def update_client_notes(request, pk):
    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=pk)
    helper = ResponseHelper(request)

    if request.method == "POST":
        update_client_notes_for_client(
            client=client,
            actor=request.user,
            notes=request.POST.get("notes", ""),
        )
        if helper.expects_json:
            return helper.success(message=_("Заметка сохранена"))
        messages.success(request, _("Заметка сохранена."))
        return redirect("clients:client_detail", pk=pk)
    return redirect("clients:client_list")


@role_required_view(*DOCUMENT_MUTATION_ROLES)
def add_document(request, client_id, doc_type):
    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=client_id)
    document_type_display = client.get_document_name_by_code(doc_type)
    helper = ResponseHelper(request)

    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            result = upload_client_document(
                client=client,
                doc_type=doc_type,
                uploaded_document=form.save(commit=False),
                actor=request.user,
                parse_requested=request.POST.get("parse_wezwanie") == "1",
                parser=parse_wezwanie,
                send_missing_email=send_missing_documents_email,
                send_appointment_email=send_appointment_notification_email,
            )
            if helper.expects_json:
                payload = {
                    "message": result.message,
                    "doc_id": result.document.id,
                    "manual_review_required": result.manual_review_required,
                }
                if result.pending_confirmation:
                    payload["pending_confirmation"] = True
                    payload["confirm_url"] = reverse(
                        "clients:confirm_wezwanie_parse",
                        kwargs={"doc_id": result.document.id},
                    )
                    payload["parsed"] = result.parsed_payload or {}
                return helper.success(**payload)

            if result.manual_review_required:
                messages.warning(request, result.message)
            else:
                messages.success(request, result.message)
            return redirect("clients:client_detail", pk=client.id)

        if helper.expects_json:
            return helper.error(
                message=_("Проверьте правильность заполнения формы."),
                errors=form.errors,
            )

    form = DocumentUploadForm()
    return render(
        request,
        "clients/add_document.html",
        {
            "form": form,
            "client": client,
            "document_type_display": document_type_display,
        },
    )


@role_required_view(*DOCUMENT_MUTATION_ROLES)
def confirm_wezwanie_parse(request, doc_id):
    document = get_object_or_404(accessible_documents_queryset(request.user, Document.objects.all()), pk=doc_id)
    helper = ResponseHelper(request)

    if request.method != "POST":
        if helper.expects_json:
            return helper.error(message=_("Недопустимый метод запроса."), status=405)
        return redirect("clients:client_detail", pk=document.client.id)

    if document.document_type not in (DocumentType.WEZWANIE, DocumentType.WEZWANIE.value):
        if helper.expects_json:
            return helper.error(message=_("Документ не является wezwanie."), status=400)
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


@role_required_view(*DOCUMENT_MUTATION_ROLES)
def document_delete(request, pk):
    document = get_object_or_404(accessible_documents_queryset(request.user, Document.objects.all()), pk=pk)
    client_id = document.client.id
    helper = ResponseHelper(request)

    if request.method == "POST":
        result = delete_client_document(document=document, actor=request.user)
        if helper.expects_json:
            return helper.success(message=_("Документ '%(name)s' удалён.") % {"name": result.document_display_name})

        messages.success(request, _("Документ '%(name)s' успешно удалён.") % {"name": result.document_display_name})
    else:
        messages.warning(request, _("Удаление возможно только через кнопку."))

    return redirect("clients:client_detail", pk=client_id)


@role_required_view(*DOCUMENT_MUTATION_ROLES)
def wniosek_attachment_delete(request, attachment_id):
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
        message = _("Отметка '%(name)s' удалена.") % {"name": result.attachment_name}
        if helper.expects_json:
            return helper.success(message=message)

        messages.success(request, message)
    else:
        messages.warning(request, _("Удаление возможно только через кнопку."))

    return redirect("clients:client_detail", pk=client_id)


@role_required_view(*DOCUMENT_MUTATION_ROLES)
def toggle_document_verification(request, doc_id):
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
                button_text=_("Снять отметку") if result.verified else _("Проверить"),
                emails_sent=result.emails_sent,
            )

        status = _("проверен") if result.verified else _("не проверен")
        message_suffix = _(" Письмо с недостающими документами отправлено.") if result.emails_sent else ""
        messages.success(
            request,
            _("Статус изменен: %(status)s.") % {"status": status} + str(message_suffix),
        )
    return redirect("clients:client_detail", pk=document.client.id)


@role_required_view(*DOCUMENT_MUTATION_ROLES)
def verify_all_documents(request, client_id):
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


@staff_required_view
def document_download(request, doc_id):
    document = get_object_or_404(
        accessible_documents_queryset(request.user, Document.objects.select_related("client")),
        pk=doc_id,
    )
    record_document_download(document=document, actor=request.user)
    filename = document.file.name.rsplit("/", 1)[-1]
    return build_protected_file_response(document.file, filename=filename, as_attachment=True)


@staff_required_view
def client_status_api(request, pk):
    """Return the latest client checklist as JSON for AJAX refreshes."""

    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=pk)
    checklist_html = render_to_string(
        "clients/partials/document_checklist.html",
        {
            "document_status_list": client.get_document_checklist(),
            "client": client,
        },
    )
    helper = ResponseHelper(request)
    return helper.success(checklist_html=checklist_html)


@staff_required_view
def client_overview_partial(request, pk):
    """Return the rendered client overview partial for AJAX refreshes."""

    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=pk)
    document_status_list = client.get_document_checklist()
    overview_html = render_to_string(
        "clients/partials/client_overview.html",
        {
            "client": client,
            "workflow_summary": client.get_workflow_summary(document_status_list=document_status_list),
        },
        request=request,
    )
    helper = ResponseHelper(request)
    return helper.success(html=overview_html)


@staff_required_view
def client_checklist_partial(request, pk):
    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=pk)
    document_status_list = client.get_document_checklist()
    response = render(
        request,
        "clients/partials/document_checklist.html",
        {
            "client": client,
            "document_status_list": document_status_list,
        },
    )
    return apply_no_store(response)
