# clients/views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q
from django import forms

# Импортируем ваши модели
from .models import Client, Document


# --- Формы ---
# Простая форма для загрузки одного файла
class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['file']
        labels = {
            'file': 'Выберите файл'
        }


# Простая форма для создания/редактирования клиента
class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = '__all__'


# --- Представления (Views) ---

def client_list(request):
    """Отображает список всех клиентов и реализует поиск."""
    query = request.GET.get('q', '')
    if query:
        clients = Client.objects.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(phone__icontains=query)
        ).distinct()
    else:
        clients = Client.objects.all().order_by('-created_at')

    return render(request, 'clients/clients_list.html', {
        'clients': clients,
        'query': query,
    })


def client_detail(request, pk):
    """
    Отображает детальную информацию о клиенте и все его документы,
    сгруппированные по типам.
    """
    client = get_object_or_404(Client, pk=pk)

    # Группируем документы для отображения в шаблоне
    documents_grouped = {}
    for doc_type_code, doc_type_name in Document.DOC_TYPES:
        documents_grouped[doc_type_name] = {
            'code': doc_type_code,
            'files': client.documents.filter(document_type=doc_type_code).order_by('-uploaded_at')
        }

    return render(request, 'clients/client_detail.html', {
        'client': client,
        'documents_grouped': documents_grouped,
    })


def client_add(request):
    """Добавление нового клиента."""
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            messages.success(request, "Клиент успешно создан!")
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm()
    return render(request, 'clients/client_form.html', {'form': form, 'title': 'Добавить клиента'})


def client_edit(request, pk):
    """Редактирование данных клиента."""
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, "Данные клиента успешно обновлены!")
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm(instance=client)
    return render(request, 'clients/client_form.html', {'form': form, 'title': 'Редактировать клиента'})


def add_document(request, client_id, doc_type):
    """Добавление одного файла для конкретного типа документа."""
    client = get_object_or_404(Client, pk=client_id)

    # Получаем человеко-читаемое имя документа для отображения
    document_type_display = dict(Document.DOC_TYPES).get(doc_type, doc_type)

    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.client = client
            document.document_type = doc_type
            document.save()
            messages.success(request, f"Документ '{document_type_display}' успешно добавлен.")
            return redirect('client_detail', pk=client.id)
    else:
        form = DocumentUploadForm()

    return render(request, 'clients/add_document.html', {
        'form': form,
        'client': client,
        'document_type_display': document_type_display
    })


def document_delete(request, pk):
    """Удаление конкретного файла документа."""
    document = get_object_or_404(Document, pk=pk)
    client_id = document.client.id
    doc_type_display = document.get_document_type_display()

    if request.method == "POST":
        document.delete()
        messages.success(request, f"Документ '{doc_type_display}' успешно удалён.")
        return redirect('client_detail', pk=client_id)

    return render(request, 'clients/document_confirm_delete.html', {'document': document})