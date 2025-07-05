from django.shortcuts import render, get_object_or_404, redirect
from .models import Document, Client
from .forms import DocumentForm
from django.contrib import messages
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Q
from .forms import ClientForm  # убедись, что у тебя есть такая форма
from .constants import DOCUMENTS_BY_BASIS_AND_LANGUAGE  # импортируй словарь, где лежат документы
from django.forms import modelformset_factory
from django.forms import inlineformset_factory
from django.forms import modelform_factory, inlineformset_factory


def home(request):
    return render(request, 'clients/home.html')


def client_search(request):
    query = request.GET.get('q', '')
    results = []

    if query:
        results = Client.objects.filter(
            first_name__icontains=query
        ) | Client.objects.filter(
            last_name__icontains=query
        ) | Client.objects.filter(
            email__icontains=query
        ) | Client.objects.filter(
            phone__icontains=query
        )

    return render(request, 'clients/search.html', {
        'query': query,
        'results': results
    })


def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)
    docs = DOCUMENTS_BY_BASIS_AND_LANGUAGE.get(client.legal_basis, {}).get(client.language, [])
    return render(request, 'clients/client_detail.html', {
        'client': client,
        'docs': docs,
    })


def edit_document(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES, instance=document)
        if form.is_valid():
            form.save()
            return redirect(document.client.get_absolute_url())  # возвращаемся к профилю клиента
    else:
        form = DocumentForm(instance=document)
    return render(request, 'clients/edit_document.html', {'form': form, 'document': document})


def document_delete(request, pk):
    document = get_object_or_404(Document, pk=pk)
    client_id = document.client.id

    if request.method == "POST":
        document.delete()
        messages.success(request, "Документ успешно удалён.")
        return redirect('client_detail', pk=client_id)  # редирект на профиль клиента

    # Если GET — показать подтверждение удаления
    return render(request, 'clients/document_confirm_delete.html', {'document': document})


def add_document(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.client = client
            document.save()
            return redirect('client_detail', pk=client.id)
    else:
        form = DocumentForm()
    return render(request, 'clients/add_document.html', {'form': form, 'client': client})


def update_documents(request, client_id):
    client = get_object_or_404(Client, pk=client_id)
    doc_choices = dict(Document.DOC_TYPES)

    if request.method == 'POST':
        for doc_type in doc_choices:
            file = request.FILES.get(f'file_{doc_type}')
            is_provided = request.POST.get(f'provided_{doc_type}') == 'on'

            document = client.documents.filter(doc_type=doc_type).first()

            if document:
                document.is_provided = is_provided
                if file:
                    document.file = file
                document.save()
            elif file or is_provided:
                Document.objects.create(
                    client=client,
                    doc_type=doc_type,
                    file=file if file else None,
                    is_provided=is_provided,
                )
        return redirect('client_detail', pk=client.id)

    return redirect('client_detail', pk=client.id)


def client_list(request):
    query = request.GET.get('q', '')  # Получаем параметр поиска из GET-запроса
    if query:
        clients = Client.objects.filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query)
        )
    else:
        clients = Client.objects.all()
    return render(request, 'clients/clients_list.html', {
        'clients': clients,
        'query': query
    })


DocumentFormSet = modelformset_factory(Document, form=DocumentForm, extra=1, can_delete=True)


def client_edit(request, pk):
    client = get_object_or_404(Client, pk=pk)
    ClientForm = modelform_factory(Client, exclude=[])
    DocumentFormSet = inlineformset_factory(Client, Document, fields=('doc_type', 'file', 'is_provided'), extra=1, can_delete=True)

    if request.method == "POST":
        form = ClientForm(request.POST, instance=client)
        formset = DocumentFormSet(request.POST, request.FILES, instance=client)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm(instance=client)
        formset = DocumentFormSet(instance=client)

    return render(request, 'clients/client_edit.html', {
        'form': form,
        'formset': formset,
        'client': client,
    })


def client_add(request):
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm()
    return render(request, 'clients/client_add.html', {'form': form})
