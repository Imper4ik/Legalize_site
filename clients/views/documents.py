from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.dateparse import parse_date

from clients.constants import DocumentType
from clients.forms import DocumentUploadForm
from clients.models import Client, Document
from clients.services.notifications import send_missing_documents_email, send_appointment_notification_email
from clients.services.responses import ResponseHelper, apply_no_store
from clients.services.wezwanie_parser import parse_wezwanie
from clients.views.base import staff_required_view


@staff_required_view
def update_client_notes(request, pk):
    client = get_object_or_404(Client, pk=pk)
    helper = ResponseHelper(request)

    if request.method == 'POST':
        client.notes = request.POST.get('notes', '')
        client.save()
        if helper.expects_json:
            return helper.success(message='Заметка сохранена')
        messages.success(request, "Заметка сохранена.")
        return redirect('clients:client_detail', pk=pk)
    return redirect('clients:client_list')


@staff_required_view
def add_document(request, client_id, doc_type):
    client = get_object_or_404(Client, pk=client_id)
    document_type_display = client.get_document_name_by_code(doc_type)
    helper = ResponseHelper(request)

    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.client = client
            document.document_type = doc_type
            document.save()

            auto_updates: list[str] = []
            parse_requested = request.POST.get("parse_wezwanie") == "1"
            is_wezwanie = doc_type == DocumentType.WEZWANIE or doc_type == DocumentType.WEZWANIE.value
    # Check if the document type is Wezwanie (using ID or string comparison depending on implementation)
    # Ideally should use checking against DocumentType.WEZWANIE but we rely on form/hidden input often.
    # Here we rely on helper logic or simple check.
    
            if is_wezwanie and parse_requested:
                print(f"DEBUG: Starting Wezwanie parsing for doc {document.id}...", flush=True)
                try:
                    parsed = parse_wezwanie(document.file.path)
                    print(f"DEBUG: Parsing finished. Text len: {len(parsed.text)}", flush=True)
                except Exception as e:
                    print(f"DEBUG: Parsing CRASHED: {e}", flush=True)
                    raise e
                
                document.awaiting_confirmation = True
                has_text = bool(parsed.text.strip())
                has_key_fields = any(
                    [
                        parsed.case_number,
                        parsed.fingerprints_date,
                        parsed.decision_date,
                        parsed.full_name,
                    ]
                )
                if not (has_text or has_key_fields):
                    if helper.expects_json:
                        return helper.error(
                            message=(
                                "Не удалось распознать wezwanie: нет текста. "
                                "Проверьте, что OCR доступен и файл читаемый."
                            )
                        )
                    messages.error(
                        request,
                        "Не удалось распознать wezwanie: нет текста. "
                        "Проверьте, что OCR доступен и файл читаемый.",
                    )
                    return redirect("clients:client_detail", pk=client.id)
                document.awaiting_confirmation = True
                document.save(update_fields=["awaiting_confirmation"])

                first_name = ""
                last_name = ""
                if parsed.full_name:
                    name_parts = parsed.full_name.split()
                    if len(name_parts) >= 2:
                        first_name = name_parts[0]
                        last_name = " ".join(name_parts[1:])

                return helper.success(
                    message="Документ загружен. Подтвердите распознанные данные.",
                    doc_id=document.id,
                    pending_confirmation=True,
                    confirm_url=reverse(
                        "clients:confirm_wezwanie_parse",
                        kwargs={"doc_id": document.id},
                    ),
                    parsed={
                        "full_name": parsed.full_name or "",
                        "first_name": first_name,
                        "last_name": last_name,
                        "case_number": parsed.case_number or "",
                        "fingerprints_date": parsed.fingerprints_date.isoformat()
                        if parsed.fingerprints_date
                        else "",
                        "fingerprints_date_display": parsed.fingerprints_date.strftime("%d.%m.%Y")
                        if parsed.fingerprints_date
                        else "",
                        "fingerprints_time": parsed.fingerprints_time or "",
                        "fingerprints_location": parsed.fingerprints_location or "",
                        "decision_date": parsed.decision_date.isoformat()
                        if parsed.decision_date
                        else "",
                        "decision_date_display": parsed.decision_date.strftime("%d.%m.%Y")
                        if parsed.decision_date
                        else "",
                    },
                )

            if is_wezwanie:
                parsed = parse_wezwanie(document.file.path)

                updated_fields = []
                if parsed.case_number and parsed.case_number != client.case_number:
                    client.case_number = parsed.case_number
                    updated_fields.append("case_number")
                    auto_updates.append(f"номер дела: {parsed.case_number}")
                    
                if parsed.fingerprints_date and parsed.fingerprints_date != client.fingerprints_date:
                    client.fingerprints_date = parsed.fingerprints_date
                    updated_fields.append("fingerprints_date")
                    auto_updates.append(
                        f"дата сдачи отпечатков: {parsed.fingerprints_date.strftime('%d.%m.%Y')}"
                    )
                
                if parsed.fingerprints_time and parsed.fingerprints_time != str(client.fingerprints_time):
                    client.fingerprints_time = parsed.fingerprints_time
                    updated_fields.append("fingerprints_time")
                    auto_updates.append(f"время отпечатков: {parsed.fingerprints_time}")

                if parsed.fingerprints_location and parsed.fingerprints_location != client.fingerprints_location:
                    client.fingerprints_location = parsed.fingerprints_location
                    updated_fields.append("fingerprints_location")
                    auto_updates.append(f"место отпечатков: {parsed.fingerprints_location}")

                if parsed.decision_date and parsed.decision_date != client.decision_date:
                    client.decision_date = parsed.decision_date
                    updated_fields.append("decision_date")
                    auto_updates.append(
                        f"дата децизии: {parsed.decision_date.strftime('%d.%m.%Y')}"
                    )
                
                if parsed.full_name and (not client.first_name or not client.last_name):
                    # Only update name if it's empty
                    name_parts = parsed.full_name.split()
                    if len(name_parts) >= 2:
                        client.first_name = name_parts[0]
                        client.last_name = " ".join(name_parts[1:])
                        updated_fields.extend(["first_name", "last_name"])
                        auto_updates.append(f"ФИО: {parsed.full_name}")

                if updated_fields:
                    client.save(update_fields=updated_fields)

                if parsed.required_documents:
                    doc_labels = []
                    for doc_code in parsed.required_documents:
                        try:
                            doc_labels.append(str(DocumentType(doc_code).label))
                        except ValueError:
                            doc_labels.append(doc_code)
                    if doc_labels:
                        auto_updates.append(f"Обнаружен запрос документов: {', '.join(doc_labels)}")

                emails_sent = send_missing_documents_email(client)
                if emails_sent:
                    auto_updates.append("отправлено письмо с недостающими документами")

                if parsed.wezwanie_type == "fingerprints" and parsed.fingerprints_date:
                    apt_email_sent = send_appointment_notification_email(client)
                    if apt_email_sent:
                        auto_updates.append("отправлено уведомление о встрече")


            success_message = f"Документ '{document_type_display}' успешно добавлен."
            if auto_updates:
                success_message = success_message + " " + " ; ".join(auto_updates)

            if helper.expects_json:
                return helper.success(
                    message=success_message,
                    doc_id=document.id,
                )

            messages.success(request, success_message)
            return redirect('clients:client_detail', pk=client.id)
        if helper.expects_json:
            return helper.error(
                message='Проверьте правильность заполнения формы.',
                errors=form.errors,
            )

    form = DocumentUploadForm()
    return render(request, 'clients/add_document.html', {
        'form': form, 'client': client, 'document_type_display': document_type_display
    })


@staff_required_view
def confirm_wezwanie_parse(request, doc_id):
    document = get_object_or_404(Document, pk=doc_id)
    helper = ResponseHelper(request)

    if request.method != "POST":
        if helper.expects_json:
            return helper.error(message="Недопустимый метод запроса.", status=405)
        return redirect("clients:client_detail", pk=document.client.id)

    if document.document_type not in (DocumentType.WEZWANIE, DocumentType.WEZWANIE.value):
        if helper.expects_json:
            return helper.error(message="Документ не является wezwanie.", status=400)
        messages.error(request, "Документ не является wezwanie.")
        return redirect("clients:client_detail", pk=document.client.id)

    client = document.client
    updated_fields: list[str] = []
    auto_updates: list[str] = []

    first_name = (request.POST.get("first_name") or "").strip()
    last_name = (request.POST.get("last_name") or "").strip()
    case_number = (request.POST.get("case_number") or "").strip()
    fingerprints_date_raw = (request.POST.get("fingerprints_date") or "").strip()
    fingerprints_time = (request.POST.get("fingerprints_time") or "").strip()
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
        auto_updates.append(f"номер дела: {case_number}")

    fingerprints_date = parse_date(fingerprints_date_raw) if fingerprints_date_raw else None
    if fingerprints_date and fingerprints_date != client.fingerprints_date:
        client.fingerprints_date = fingerprints_date
        updated_fields.append("fingerprints_date")
        auto_updates.append(f"дата сдачи отпечатков: {fingerprints_date.strftime('%d.%m.%Y')}")

    if fingerprints_time and fingerprints_time != str(client.fingerprints_time):
        client.fingerprints_time = fingerprints_time
        updated_fields.append("fingerprints_time")
        auto_updates.append(f"время отпечатков: {fingerprints_time}")

    if fingerprints_location and fingerprints_location != client.fingerprints_location:
        client.fingerprints_location = fingerprints_location
        updated_fields.append("fingerprints_location")
        auto_updates.append(f"место отпечатков: {fingerprints_location}")

    decision_date = parse_date(decision_date_raw) if decision_date_raw else None
    if decision_date and decision_date != client.decision_date:
        client.decision_date = decision_date
        updated_fields.append("decision_date")
        auto_updates.append(f"дата децизии: {decision_date.strftime('%d.%m.%Y')}")

    if updated_fields:
        client.save(update_fields=updated_fields)

    document.awaiting_confirmation = False
    document.save(update_fields=["awaiting_confirmation"])

    parsed = parse_wezwanie(document.file.path)
    if parsed.required_documents:
        doc_labels = []
        for doc_code in parsed.required_documents:
            try:
                doc_labels.append(str(DocumentType(doc_code).label))
            except ValueError:
                doc_labels.append(doc_code)
        if doc_labels:
            auto_updates.append(f"Обнаружен запрос документов: {', '.join(doc_labels)}")

    emails_sent = send_missing_documents_email(client)
    if emails_sent:
        auto_updates.append("отправлено письмо с недостающими документами")

    if client.fingerprints_date:
        apt_email_sent = send_appointment_notification_email(client)
        if apt_email_sent:
            auto_updates.append("отправлено уведомление о встрече")

    success_message = "Данные wezwanie подтверждены."
    if auto_updates:
        success_message = f"{success_message} " + " ; ".join(auto_updates)

    if helper.expects_json:
        return helper.success(message=success_message)

    messages.success(request, success_message)
    return redirect("clients:client_detail", pk=client.id)


@staff_required_view
def document_delete(request, pk):
    document = get_object_or_404(Document, pk=pk)
    client_id = document.client.id
    helper = ResponseHelper(request)

    if request.method == "POST":
        doc_type_display = document.display_name
        document.delete()  # Сигнал позаботится об удалении файла

        if helper.expects_json:
            return helper.success(message=f"Документ '{doc_type_display}' удалён.")

        messages.success(request, f"Документ '{doc_type_display}' успешно удалён.")
    else:
        messages.warning(request, "Удаление возможно только через кнопку.")

    return redirect('clients:client_detail', pk=client_id)


@staff_required_view
def toggle_document_verification(request, doc_id):
    """
    Переключает статус верификации документа. Поддерживает AJAX.
    """
    document = get_object_or_404(Document, pk=doc_id)
    helper = ResponseHelper(request)
    if request.method == 'POST':
        was_verified = document.verified
        document.verified = not document.verified
        document.save()

        emails_sent = 0
        if document.verified and not was_verified:
            emails_sent = send_missing_documents_email(document.client)

        if helper.expects_json:
            return helper.success(
                verified=document.verified,
                button_text="Снять отметку" if document.verified else "Проверить",
                emails_sent=bool(emails_sent),
            )

        status = "проверен" if document.verified else "не проверен"
        message_suffix = " Письмо с недостающими документами отправлено." if emails_sent else ""
        messages.success(request, f"Статус документа изменен на '{status}'.{message_suffix}")
    return redirect('clients:client_detail', pk=document.client.id)


@staff_required_view
def verify_all_documents(request, client_id):
    """Отмечает все загруженные документы клиента как проверенные одним действием."""

    client = get_object_or_404(Client, pk=client_id)
    helper = ResponseHelper(request)

    if request.method != 'POST':
        return redirect('clients:client_detail', pk=client.id)

    updated_count = client.documents.filter(verified=False).update(verified=True)

    emails_sent = 0
    if updated_count:
        emails_sent = send_missing_documents_email(client)

    if helper.expects_json:
        return helper.success(
            verified_count=updated_count,
            emails_sent=bool(emails_sent),
        )

    if updated_count:
        message = f"Отмечено {updated_count} документов как проверенные."
        if emails_sent:
            message += " Письмо с недостающими документами отправлено."
        messages.success(request, message)
    else:
        messages.info(request, "Все загруженные документы уже проверены.")

    return redirect('clients:client_detail', pk=client.id)


@staff_required_view
def client_status_api(request, pk):
    """Возвращает актуальный чеклист клиента в формате JSON для 'живого' обновления."""
    client = get_object_or_404(Client, pk=pk)

    checklist_html = render_to_string('clients/partials/document_checklist.html', {
        'document_status_list': client.get_document_checklist(),
        'client': client
    })
    helper = ResponseHelper(request)
    return helper.success(checklist_html=checklist_html)


@staff_required_view
def client_overview_partial(request, pk):
    """Возвращает HTML со сводной информацией о клиенте для автообновления на странице сотрудника."""

    client = get_object_or_404(Client, pk=pk)
    overview_html = render_to_string(
        'clients/partials/client_overview.html',
        {
            'client': client,
        },
        request=request,
    )
    helper = ResponseHelper(request)
    return helper.success(html=overview_html)


@staff_required_view
def client_checklist_partial(request, pk):
    client = get_object_or_404(Client, pk=pk)
    document_status_list = client.get_document_checklist()
    response = render(request, 'clients/partials/document_checklist.html', {
        'client': client,
        'document_status_list': document_status_list
    })
    return apply_no_store(response)
