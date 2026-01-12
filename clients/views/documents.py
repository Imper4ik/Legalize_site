from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from clients.constants import DocumentType
from clients.forms import DocumentUploadForm
from clients.models import Client, Document
from clients.services.notifications import send_missing_documents_email
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
            if doc_type == DocumentType.WEZWANIE or doc_type == DocumentType.WEZWANIE.value:
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

                emails_sent = send_missing_documents_email(client)
                if emails_sent:
                    auto_updates.append("отправлено письмо с недостающими документами")


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
