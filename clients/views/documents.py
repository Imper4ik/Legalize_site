from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from clients.forms import DocumentUploadForm
from clients.models import Client, Document
from clients.services.responses import ResponseHelper, apply_no_store
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

            if helper.expects_json:
                return helper.success(
                    message=f"Документ '{document_type_display}' успешно добавлен.",
                    doc_id=document.id,
                )

            messages.success(request, f"Документ '{document_type_display}' успешно добавлен.")
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
        document.verified = not document.verified
        document.save()

        if helper.expects_json:
            return helper.success(
                verified=document.verified,
                button_text="Снять отметку" if document.verified else "Проверить",
            )

        status = "проверен" if document.verified else "не проверен"
        messages.success(request, f"Статус документа изменен на '{status}'.")
    return redirect('clients:client_detail', pk=document.client.id)


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
    overview_html = render_to_string('clients/partials/client_overview.html', {'client': client}, request=request)
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
