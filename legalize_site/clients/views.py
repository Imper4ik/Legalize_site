# clients/views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q
from datetime import datetime
from dateutil.relativedelta import relativedelta
from collections import defaultdict
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required

# Импортируем модели, константы и наши кастомные формы
from .models import Client, Document, Reminder
from .constants import DOCUMENT_CHECKLIST
from .forms import ClientForm, DocumentUploadForm
from .forms import ClientForm, DocumentUploadForm, PaymentForm
from django.utils import timezone


# --- Представления (Views) ---

@login_required
def client_list(request):
    query = request.GET.get('q', '')
    if query:
        clients = Client.objects.filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query) |
            Q(email__icontains=query) | Q(phone__icontains=query) | Q(case_number__icontains=query)
        ).distinct()
    else:
        clients = Client.objects.all().order_by('-created_at')
    return render(request, 'clients/clients_list.html', {'clients': clients, 'query': query})


@login_required
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


@login_required
def client_add(request):
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            messages.success(request, "Клиент успешно создан!")
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm()
    return render(request, 'clients/client_form.html', {'form': form, 'title': 'Добавить клиента'})


@login_required
def client_edit(request, pk):
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


@login_required
def client_delete(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        client_name = client.first_name + " " + client.last_name
        client.delete()
        messages.success(request, f"Клиент {client_name} был успешно удалён.")
        return redirect('client_list')
    return render(request, 'clients/client_confirm_delete.html', {'client': client})


@login_required
def update_client_notes(request, pk):
    if request.method == 'POST':
        client = get_object_or_404(Client, pk=pk)
        client.notes = request.POST.get('notes', '')
        client.save()
        messages.success(request, f"Заметка для клиента {client.first_name} сохранена.")
    return redirect('client_list')


@login_required
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


@login_required
def document_delete(request, pk):
    document = get_object_or_404(Document, pk=pk)
    client_id = document.client.id
    doc_type_display = document.get_document_type_display()
    if request.method == "POST":
        document.delete()
        messages.success(request, f"Документ '{doc_type_display}' успешно удалён.")
        return redirect('client_detail', pk=client_id)
    return render(request, 'clients/document_confirm_delete.html', {'document': document})


@login_required
def calculator_view(request):
    LIVING_ALLOWANCE = 1010
    TICKET_BORDER = 500
    TICKET_NO_BORDER = 2500
    MAX_MONTHS_LIVING = 15
    EUR_TO_PLN_RATE = 4.24

    context = {
        'living_allowance': LIVING_ALLOWANCE,
        'eur_to_pln_rate': EUR_TO_PLN_RATE,
        'max_months_living': MAX_MONTHS_LIVING
    }

    if request.method == 'POST':
        try:
            tuition_fee = float(request.POST.get('tuition_fee', 0))
            if request.POST.get('tuition_currency') == 'EUR':
                tuition_fee *= EUR_TO_PLN_RATE

            fee_type = request.POST.get('fee_type')
            if fee_type == 'per_semester':
                monthly_tuition = tuition_fee / 5
            elif fee_type == 'per_year':
                monthly_tuition = tuition_fee / 10
            else:
                monthly_tuition = tuition_fee

            monthly_rent_and_bills = float(request.POST.get('rent_and_bills', 0))
            if request.POST.get('rent_currency') == 'EUR':
                monthly_rent_and_bills *= EUR_TO_PLN_RATE

            total_end_date_str = request.POST.get('total_end_date')
            total_end_date = datetime.strptime(total_end_date_str, '%d.%m.%Y')

            total_period_delta = relativedelta(total_end_date, datetime.now())
            total_months_real = total_period_delta.years * 12 + total_period_delta.months + 1
            months_for_calc = min(total_months_real, MAX_MONTHS_LIVING)

            has_border = request.POST.get('has_border')
            return_ticket = TICKET_BORDER if has_border else TICKET_NO_BORDER

            total_monthly_costs = monthly_rent_and_bills + monthly_tuition + LIVING_ALLOWANCE
            total_base_cost = total_monthly_costs * months_for_calc
            final_total_required = total_base_cost + return_ticket

            context['results'] = {
                'monthly_rent_and_bills': f"{monthly_rent_and_bills:,.2f}".replace(",", " "),
                'monthly_tuition_calculated': f"{monthly_tuition:,.2f}".replace(",", " "),
                'living_allowance': f"{LIVING_ALLOWANCE:,.2f}".replace(",", " "),
                'total_monthly_costs': f"{total_monthly_costs:,.2f}".replace(",", " "),
                'months_for_calc': months_for_calc,
                'total_base_cost': f"{total_base_cost:,.2f}".replace(",", " "),
                'return_ticket': f"{return_ticket:,.2f}".replace(",", " "),
                'final_total_required': f"{final_total_required:,.2f}".replace(",", " "),
            }
            context['form_data'] = request.POST

        except (ValueError, TypeError, AttributeError):
            messages.error(request, "Ошибка. Пожалуйста, заполните все поля корректными значениями.")

    return render(request, 'clients/calculator.html', context)


@login_required
def client_print_view(request, pk):
    client = get_object_or_404(Client, pk=pk)
    return render(request, 'clients/client_printable.html', {'client': client})


def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, f'Аккаунт для {username} успешно создан! Теперь вы можете войти.')
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'clients/register.html', {'form': form})


@login_required
def add_payment(request, client_id):
    client = get_object_or_404(Client, pk=client_id)
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.client = client
            payment.save()
            messages.success(request, "Платёж успешно добавлен.")
            return redirect('client_detail', pk=client.id)
    # Если форма невалидна или это GET-запрос, просто вернёмся на страницу клиента.
    # Обработка ошибок валидации будет происходить на стороне клиента, если понадобится.
    return redirect('client_detail', pk=client.id)


@login_required
def reminder_list(request):
    # Показываем только активные напоминания с датой в будущем
    reminders = Reminder.objects.filter(is_active=True, due_date__gte=timezone.now().date())
    return render(request, 'clients/reminder_list.html', {'reminders': reminders})