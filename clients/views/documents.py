from __future__ import annotations

import logging

from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.dateparse import parse_date, parse_time
from django.utils.translation import gettext as _

from clients.constants import DocumentType
from clients.forms import DocumentUploadForm
from clients.models import Client, Document, DocumentVersion, WniosekAttachment
from clients.services.activity import changed_field_labels, log_client_activity
from clients.services.notifications import (
    send_appointment_notification_email,
    send_missing_documents_email,
)
from clients.services.responses import ResponseHelper, apply_no_store
from clients.services.wezwanie_parser import parse_wezwanie
from clients.views.base import staff_required_view

logger = logging.getLogger(__name__)


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
            existing_doc = Document.objects.filter(client=client, document_type=doc_type).first()
            if existing_doc:
                # Create a version from the old file if it exists
                if existing_doc.file:
                    current_max = existing_doc.versions.aggregate(
                        max_v=__import__("django.db.models", fromlist=["Max"]).Max("version_number")
                    )["max_v"] or 0
                    
                    DocumentVersion.objects.create(
                        document=existing_doc,
                        file=existing_doc.file,
                        version_number=current_max + 1,
                        uploaded_by=existing_doc.client.user if hasattr(existing_doc.client, "user") else None,
                        comment=_("Автоматическая архивация при загрузке нового файла"),
                        file_name=existing_doc.file.name.split("/")[-1],
                        file_size=existing_doc.file.size,
                    )
                document = form.save(commit=False)
                existing_doc.file = document.file
                if document.expiry_date:
                    existing_doc.expiry_date = document.expiry_date
                existing_doc.verified = False
                existing_doc.ocr_status = "skipped"
                existing_doc.ocr_name_mismatch = False
                existing_doc.save()
                document = existing_doc
            else:
                document = form.save(commit=False)
                document.client = client
                document.document_type = doc_type
                document.save()
                
            log_client_activity(
                client=client,
                actor=request.user,
                event_type="document_uploaded",
                summary=f"Загружен документ: {document.display_name}",
                metadata={"document_id": document.id, "document_type": document.document_type},
                document=document,
            )

            auto_updates: list[str] = []
            manual_review_required = False
            parse_requested = request.POST.get("parse_wezwanie") == "1"
            is_wezwanie = doc_type in (DocumentType.WEZWANIE, DocumentType.WEZWANIE.value)

            if is_wezwanie and parse_requested:
                try:
                    parsed = parse_wezwanie(document.file.path)
                    document.ocr_status = "success"
                except Exception:
                    logger.exception("Wezwanie parsing failed for document %s", document.id)
                    document.ocr_status = "failed"
                    manual_review_required = True
                else:
                    has_text = bool(parsed.text.strip())
                    has_key_fields = any(
                        [
                            parsed.case_number,
                            parsed.fingerprints_date,
                            parsed.decision_date,
                            parsed.full_name,
                        ]
                    )
                    if has_text or has_key_fields:
                        if parsed.full_name and client.first_name and client.last_name:
                            # Simple fuzzy check
                            full_client_name = f"{client.first_name} {client.last_name}".lower()
                            if client.first_name.lower() not in parsed.full_name.lower() or client.last_name.lower() not in parsed.full_name.lower():
                                document.ocr_name_mismatch = True
                                
                        document.awaiting_confirmation = True
                        document.save(update_fields=["awaiting_confirmation", "ocr_status", "ocr_name_mismatch"])
                        return helper.success(
                            message=_("Документ загружен. Подтвердите распознанные данные."),
                            doc_id=document.id,
                            pending_confirmation=True,
                            confirm_url=reverse(
                                "clients:confirm_wezwanie_parse",
                                kwargs={"doc_id": document.id},
                            ),
                            parsed=_build_wezwanie_payload(parsed),
                        )
                    manual_review_required = True

            if is_wezwanie and not parse_requested:
                try:
                    parsed = parse_wezwanie(document.file.path)
                    document.ocr_status = "success"
                except Exception:
                    logger.exception("Background wezwanie parsing failed for document %s", document.id)
                    document.ocr_status = "failed"
                    manual_review_required = True
                else:
                    updated_fields: list[str] = []
                    if parsed.case_number and parsed.case_number != client.case_number:
                        client.case_number = parsed.case_number
                        updated_fields.append("case_number")
                        auto_updates.append(_("номер дела: %(val)s") % {"val": parsed.case_number})

                    if parsed.fingerprints_date and parsed.fingerprints_date != client.fingerprints_date:
                        client.fingerprints_date = parsed.fingerprints_date
                        updated_fields.append("fingerprints_date")
                        auto_updates.append(
                            _("дата сдачи отпечатков: %(val)s")
                            % {"val": parsed.fingerprints_date.strftime("%d.%m.%Y")}
                        )

                    parsed_fingerprints_time = parse_time(parsed.fingerprints_time or "")
                    if parsed_fingerprints_time and parsed_fingerprints_time != client.fingerprints_time:
                        client.fingerprints_time = parsed_fingerprints_time
                        updated_fields.append("fingerprints_time")

                    if (
                        parsed.fingerprints_location
                        and parsed.fingerprints_location != (client.fingerprints_location or "")
                    ):
                        client.fingerprints_location = parsed.fingerprints_location
                        updated_fields.append("fingerprints_location")

                    if parsed.decision_date and parsed.decision_date != client.decision_date:
                        client.decision_date = parsed.decision_date
                        updated_fields.append("decision_date")
                        auto_updates.append(
                            _("дата децизии: %(val)s")
                            % {"val": parsed.decision_date.strftime("%d.%m.%Y")}
                        )

                    if parsed.full_name and (not client.first_name or not client.last_name):
                        name_parts = parsed.full_name.split()
                        if len(name_parts) >= 2:
                            client.first_name = name_parts[0]
                            client.last_name = " ".join(name_parts[1:])
                            updated_fields.extend(["first_name", "last_name"])
                            auto_updates.append(_("ФИО: %(val)s") % {"val": parsed.full_name})

                    if updated_fields:
                        client.save(update_fields=updated_fields)
                        log_client_activity(
                            client=client,
                            actor=request.user,
                            event_type="client_updated",
                            summary="Данные клиента обновлены после распознавания документа",
                            details=", ".join(changed_field_labels(client, updated_fields)),
                            metadata={"changed_fields": updated_fields, "source": "document_parse"},
                            document=document,
                        )

                    if parsed.full_name and client.first_name and client.last_name:
                        if client.first_name.lower() not in parsed.full_name.lower() or client.last_name.lower() not in parsed.full_name.lower():
                            document.ocr_name_mismatch = True
                    document.save(update_fields=["ocr_status", "ocr_name_mismatch"])

                    _append_required_documents_update(parsed, auto_updates)

                    emails_sent = send_missing_documents_email(client)
                    if emails_sent:
                        auto_updates.append(_("отправлено письмо с недостающими документами"))

                    if parsed.wezwanie_type == "fingerprints" and parsed.fingerprints_date:
                        apt_email_sent = send_appointment_notification_email(client)
                        if apt_email_sent:
                            auto_updates.append(_("отправлено уведомление о встрече"))

            success_message = _("Документ '%(name)s' успешно добавлен.") % {
                "name": document_type_display
            }
            if manual_review_required:
                success_message = f"{success_message} {MANUAL_WEZWANIE_REVIEW_MESSAGE}"
            if auto_updates:
                success_message = success_message + " " + " ; ".join(auto_updates)

            if helper.expects_json:
                return helper.success(
                    message=success_message,
                    doc_id=document.id,
                    manual_review_required=manual_review_required,
                )

            if manual_review_required:
                messages.warning(request, success_message)
            else:
                messages.success(request, success_message)
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

    client = document.client
    updated_fields: list[str] = []
    auto_updates: list[str] = []
    manual_review_required = False

    first_name = (request.POST.get("first_name") or "").strip()
    last_name = (request.POST.get("last_name") or "").strip()
    case_number = (request.POST.get("case_number") or "").strip()
    fingerprints_date_raw = (request.POST.get("fingerprints_date") or "").strip()
    fingerprints_time_raw = (request.POST.get("fingerprints_time") or "").strip()
    fingerprints_location = (request.POST.get("fingerprints_location") or "").strip()
    decision_date_raw = (request.POST.get("decision_date") or "").strip()

    if first_name and first_name != client.first_name:
        client.first_name = first_name
        updated_fields.append("first_name")
    if last_name and last_name != client.last_name:
        client.last_name = last_name
        updated_fields.append("last_name")
    if case_number and case_number != client.case_number:
        client.case_number = case_number
        updated_fields.append("case_number")
        auto_updates.append(_("номер дела: %(val)s") % {"val": case_number})

    fingerprints_date = parse_date(fingerprints_date_raw) if fingerprints_date_raw else None
    if fingerprints_date and fingerprints_date != client.fingerprints_date:
        client.fingerprints_date = fingerprints_date
        updated_fields.append("fingerprints_date")
        auto_updates.append(
            _("дата сдачи отпечатков: %(val)s")
            % {"val": fingerprints_date.strftime("%d.%m.%Y")}
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
        auto_updates.append(_("дата децизии: %(val)s") % {"val": decision_date.strftime("%d.%m.%Y")})

    if updated_fields:
        client.save(update_fields=updated_fields)
        log_client_activity(
            client=client,
            actor=request.user,
            event_type="client_updated",
            summary="Подтверждены данные из wezwanie",
            details=", ".join(changed_field_labels(client, updated_fields)),
            metadata={"changed_fields": updated_fields, "source": "wezwanie_confirmation"},
            document=document,
        )

    document.awaiting_confirmation = False
    document.save(update_fields=["awaiting_confirmation"])

    try:
        parsed = parse_wezwanie(document.file.path)
    except Exception:
        logger.exception("Wezwanie parsing failed during confirmation for document %s", document.id)
        manual_review_required = True
    else:
        _append_required_documents_update(parsed, auto_updates)

    emails_sent = send_missing_documents_email(client)
    if emails_sent:
        auto_updates.append(_("отправлено письмо с недостающими документами"))

    if client.fingerprints_date:
        apt_email_sent = send_appointment_notification_email(client)
        if apt_email_sent:
            auto_updates.append(_("отправлено уведомление о встрече"))

    success_message = _("Данные wezwanie подтверждены.")
    if manual_review_required:
        success_message = f"{success_message} {MANUAL_WEZWANIE_REVIEW_MESSAGE}"
    if auto_updates:
        success_message = f"{success_message} " + " ; ".join(auto_updates)

    if helper.expects_json:
        return helper.success(
            message=success_message,
            manual_review_required=manual_review_required,
        )

    if manual_review_required:
        messages.warning(request, success_message)
    else:
        messages.success(request, success_message)
    return redirect("clients:client_detail", pk=client.id)


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
    return FileResponse(file_handle, as_attachment=False, filename=filename)


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
