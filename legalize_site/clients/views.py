# clients/views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q
from datetime import datetime
from dateutil.relativedelta import relativedelta
from collections import defaultdict

# Импортируем модели и константы
from .models import Client, Document
from .constants import DOCUMENT_CHECKLIST
# Импортируем наши правильные формы из файла forms.py
from .forms import ClientForm, DocumentUploadForm


# --- Представления (Views) ---

def client_list(request):
    query = request.GET.get('q', '')
    if query:
        clients = Client.objects.filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query) |
            Q(email__icontains=query) | Q(phone__icontains=query)
        ).distinct()
    else:
        clients = Client.objects.all().order_by('-created_at')
    return render(request, 'clients/clients_list.html', {'clients': clients, 'query': query})


def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)
    checklist_key = (client.application_purpose, client.language)
    required_docs_list = DOCUMENT_CHECKLIST.get(checklist_key, [])
    uploaded_docs = defaultdict(list)
    for doc in client.documents.all().order_by('-uploaded_at'):
        uploaded_docs[doc.document_type].append(doc)
    document_status_list = []
    for doc_code, doc_name in required_docs_list:
        docs_for_type = uploaded_docs.get(doc_code, [])
        document_status_list.append({
            'code': doc_code,
            'name': doc_name,
            'is_uploaded': len(docs_for_type) > 0,
            'documents': docs_for_type,
        })
    return render(request, 'clients/client_detail.html', {
        'client': client,
        'document_status_list': document_status_list,
    })


def client_add(request):
    if request.method == 'POST':
        form = ClientForm(request.POST) # <-- Теперь используется правильная форма из forms.py
        if form.is_valid():
            client = form.save()
            messages.success(request, "Клиент успешно создан!")
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm()
    return render(request, 'clients/client_form.html', {'form': form, 'title': 'Добавить клиента'})


def client_edit(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client) # <-- Теперь используется правильная форма из forms.py
        if form.is_valid():
            form.save()
            messages.success(request, "Данные клиента успешно обновлены!")
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm(instance=client)
    return render(request, 'clients/client_form.html', {'form': form, 'title': 'Редактировать клиента'})


def client_delete(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        client_name = client.first_name + " " + client.last_name
        client.delete()
        messages.success(request, f"Клиент {client_name} был успешно удалён.")
        return redirect('client_list')
    return render(request, 'clients/client_confirm_delete.html', {'client': client})


def update_client_notes(request, pk):
    if request.method == 'POST':
        client = get_object_or_404(Client, pk=pk)
        client.notes = request.POST.get('notes', '')
        client.save()
        messages.success(request, f"Заметка для клиента {client.first_name} сохранена.")
    return redirect('client_list')


def add_document(request, client_id, doc_type):
    client = get_object_or_404(Client, pk=client_id)
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
    return render(request, 'clients/add_document.html',
                  {'form': form, 'client': client, 'document_type_display': document_type_display})


def document_delete(request, pk):
    document = get_object_or_404(Document, pk=pk)
    client_id = document.client.id
    doc_type_display = document.get_document_type_display()
    if request.method == "POST":
        document.delete()
        messages.success(request, f"Документ '{doc_type_display}' успешно удалён.")
        return redirect('client_detail', pk=client_id)
    return render(request, 'clients/document_confirm_delete.html', {'document': document})


def calculator_view(request):
    LIVING_COST_SINGLE = 776
    LIVING_COST_FAMILY = 600
    context = {'living_cost_single': LIVING_COST_SINGLE, 'living_cost_family': LIVING_COST_FAMILY}
    if request.method == 'POST':
        try:
            start_date_str = request.POST.get('start_date')
            end_date_str = request.POST.get('end_date')
            monthly_fee = float(request.POST.get('monthly_fee', 0))
            start_date = datetime.strptime(start_date_str, '%d.%m.%Y')
            end_date = datetime.strptime(end_date_str, '%d.%m.%Y')
            delta = relativedelta(end_date, start_date)
            num_months_tuition = delta.years * 12 + delta.months + 1
            total_tuition = num_months_tuition * monthly_fee
            rent = float(request.POST.get('rent', 0))
            num_people = int(request.POST.get('num_people', 1))
            months_living = int(request.POST.get('months_living', 12))
            return_ticket = float(request.POST.get('return_ticket', 2500))

            if num_people == 1:
                living_costs_per_month = LIVING_COST_SINGLE
            else:
                living_costs_per_month = LIVING_COST_SINGLE + (LIVING_COST_FAMILY * (num_people - 1))

            total_living_expenses = (rent + living_costs_per_month) * months_living
            final_total_required = total_living_expenses + total_tuition + return_ticket

            context['results'] = {
                'total_living_expenses': f"{total_living_expenses:,.2f}".replace(",", " "),
                'total_tuition': f"{total_tuition:,.2f}".replace(",", " "),
                'num_months_tuition': num_months_tuition,
                'return_ticket': f"{return_ticket:,.2f}".replace(",", " "),
                'final_total_required': f"{final_total_required:,.2f}".replace(",", " "),
            }
            context['form_data'] = request.POST
        except (ValueError, TypeError, AttributeError):
            messages.error(request, "Ошибка. Пожалуйста, заполните все поля корректными значениями.")
    return render(request, 'clients/calculator.html', context)


def client_print_view(request, pk):
    client = get_object_or_404(Client, pk=pk)
    return render(request, 'clients/client_printable.html', {'client': client})