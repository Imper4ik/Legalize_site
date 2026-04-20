from __future__ import annotations

from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext as _

from clients.constants import DocumentType
from clients.forms import DocumentUploadForm
from clients.models import Client, Document, WniosekAttachment
from clients.services.activity import log_client_activity
from clients.services.document_workflow import confirm_wezwanie_document, upload_client_document
from clients.services.notifications import (
    send_appointment_notification_email,
    send_missing_documents_email,
)
from clients.services.responses import ResponseHelper, apply_no_store
from clients.services.wezwanie_parser import parse_wezwanie
from clients.views.base import staff_required_view



MANUAL_WEZWANIE_REVIEW_MESSAGE = _(
    "Документ загружен, но автоматический разбор wezwanie не удался. Требуется ручная проверка."
)


def _build_wezwanie_payload(parsed) -> dict[str, str]:
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


def _append_required_documents_update(parsed, auto_updates: list[str]) -> None:
    if not parsed or not parsed.required_documents:
        return

    doc_labels: list[str] = []
    for doc_code in parsed.required_documents:
        try:
            doc_labels.append(str(DocumentType(doc_code).label))
        except ValueError:
            doc_labels.append(doc_code)
    if doc_labels:
        auto_updates.append(
            _("Обнаружен запрос документов: %(val)s") % {"val": ", ".join(doc_labels)}
        )


@staff_required_view
def update_client_notes(request, pk):
    client = get_object_or_404(Client, pk=pk)
    helper = ResponseHelper(request)

    if request.method == "POST":
        client.notes = request.POST.get("notes", "")
        client.save()
        log_client_activity(
            client=client,
            actor=request.user,
            event_type="note_updated",
            summary="Обновлена заметка по клиенту",
        )
        if helper.expects_json:
            return helper.success(message=_("Заметка сохранена"))
        messages.success(request, _("Заметка сохранена."))
        return redirect("clients:client_detail", pk=pk)
    return redirect("clients:client_list")


@staff_required_view
def add_document(request, client_id, doc_type):
    client = get_object_or_404(Client, pk=client_id)
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


@staff_required_view
def confirm_wezwanie_parse(request, doc_id):
    document = get_object_or_404(Document, pk=doc_id)
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


@staff_required_view
def document_delete(request, pk):
    document = get_object_or_404(Document, pk=pk)
    client_id = document.client.id
    helper = ResponseHelper(request)

    if request.method == "POST":
        doc_type_display = document.display_name
        log_client_activity(
            client=document.client,
            actor=request.user,
            event_type="document_deleted",
            summary=f"Удалён документ: {doc_type_display}",
            metadata={"document_id": document.id, "document_type": document.document_type},
        )
        document.delete()

        if helper.expects_json:
            return helper.success(message=_("Документ '%(name)s' удалён.") % {"name": doc_type_display})

        messages.success(request, _("Документ '%(name)s' успешно удалён.") % {"name": doc_type_display})
    else:
        messages.warning(request, _("Удаление возможно только через кнопку."))

    return redirect("clients:client_detail", pk=client_id)


@staff_required_view
def wniosek_attachment_delete(request, attachment_id):
    attachment = get_object_or_404(
        WniosekAttachment.objects.select_related("submission", "submission__client"),
        pk=attachment_id,
    )
    submission = attachment.submission
    client_id = submission.client_id
    helper = ResponseHelper(request)

    if request.method == "POST":
        attachment_name = attachment.entered_name
        attachment.delete()

        remaining_count = submission.attachments.count()
        if remaining_count == 0:
            submission.delete()
        elif submission.attachment_count != remaining_count:
            submission.attachment_count = remaining_count
            submission.save(update_fields=["attachment_count"])

        message = _("Отметка '%(name)s' удалена.") % {"name": attachment_name}
        if helper.expects_json:
            return helper.success(message=message)

        messages.success(request, message)
    else:
        messages.warning(request, _("Удаление возможно только через кнопку."))

    return redirect("clients:client_detail", pk=client_id)


@staff_required_view
def toggle_document_verification(request, doc_id):
    """Toggle verification status for a client document."""

    document = get_object_or_404(Document, pk=doc_id)
    helper = ResponseHelper(request)
    if request.method == "POST":
        was_verified = document.verified
        document.verified = not document.verified
        document.save()
        log_client_activity(
            client=document.client,
            actor=request.user,
            event_type="document_verified",
            summary=f"Статус документа изменён: {document.display_name}",
            details="verified" if document.verified else "verification removed",
            metadata={"document_id": document.id, "verified": document.verified},
            document=document,
        )

        emails_sent = 0
        if document.verified and not was_verified:
            emails_sent = send_missing_documents_email(document.client)

        if helper.expects_json:
            return helper.success(
                verified=document.verified,
                button_text=_("Снять отметку") if document.verified else _("Проверить"),
                emails_sent=bool(emails_sent),
            )

        status = _("проверен") if document.verified else _("не проверен")
        message_suffix = _(" Письмо с недостающими документами отправлено.") if emails_sent else ""
        messages.success(
            request,
            _("Статус изменен: %(status)s.") % {"status": status} + str(message_suffix),
        )
    return redirect("clients:client_detail", pk=document.client.id)


@staff_required_view
def verify_all_documents(request, client_id):
    """Mark all uploaded documents for the client as verified."""

    client = get_object_or_404(Client, pk=client_id)
    helper = ResponseHelper(request)

    if request.method != "POST":
        return redirect("clients:client_detail", pk=client.id)

    updated_count = client.documents.filter(verified=False).update(verified=True)
    if updated_count:
        log_client_activity(
            client=client,
            actor=request.user,
            event_type="document_verified",
            summary="Все документы клиента отмечены как проверенные",
            metadata={"verified_count": updated_count},
        )

    emails_sent = 0
    if updated_count:
        emails_sent = send_missing_documents_email(client)

    if helper.expects_json:
        return helper.success(
            verified_count=updated_count,
            emails_sent=bool(emails_sent),
        )

    if updated_count:
        message = _("Отмечено %(count)s документов как проверенные.") % {"count": updated_count}
        if emails_sent:
            message += " " + _("Письмо с недостающими документами отправлено.")
        messages.success(request, message)
    else:
        messages.info(request, _("Все загруженные документы уже проверены."))

    return redirect("clients:client_detail", pk=client.id)


@staff_required_view
def document_download(request, doc_id):
    document = get_object_or_404(Document.objects.select_related("client"), pk=doc_id)
    try:
        file_handle = document.file.open("rb")
    except FileNotFoundError as exc:
        raise Http404("Document file not found") from exc

    log_client_activity(
        client=document.client,
        actor=request.user,
        event_type="document_downloaded",
        summary=f"Открыт документ: {document.display_name}",
        metadata={"document_id": document.id, "document_type": document.document_type},
        document=document,
    )
    filename = document.file.name.rsplit("/", 1)[-1]
    response = FileResponse(file_handle, as_attachment=False, filename=filename)
    return apply_no_store(response)


@staff_required_view
def client_status_api(request, pk):
    """Return the latest client checklist as JSON for AJAX refreshes."""

    client = get_object_or_404(Client, pk=pk)
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

    client = get_object_or_404(Client, pk=pk)
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
    client = get_object_or_404(Client, pk=pk)
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
