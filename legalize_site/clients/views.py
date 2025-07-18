# -*- coding: utf-8 -*-
import json

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.core.management import call_command
from collections import defaultdict
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Импорт моделей, форм и констант из вашего приложения
from .models import Client, Document, Payment, Reminder
from .forms import ClientForm, DocumentUploadForm, PaymentForm
from .constants import DOCUMENT_CHECKLIST
from .forms import PaymentForm
from .models import Client
import json

class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Миксин для проверки, что пользователь является сотрудником (staff).
    """

    def test_func(self):
        return self.request.user.is_staff


class ClientListView(StaffRequiredMixin, ListView):
    """Отображает список всех клиентов с поиском и пагинацией."""
    model = Client
    template_name = 'clients/clients_list.html'
    context_object_name = 'clients'
    paginate_by = 15

    def get_queryset(self):
        """Фильтрует клиентов по поисковому запросу."""
        query = self.request.GET.get('q', '')
        if query:
            return Client.objects.filter(
                Q(first_name__icontains=query) | Q(last_name__icontains=query) |
                Q(email__icontains=query) | Q(phone__icontains=query) | Q(case_number__icontains=query)
            ).distinct().order_by('-created_at')
        return Client.objects.all().order_by('-created_at')

    def get_context_data(self, **kwargs):
        """Добавляет поисковый запрос в контекст."""
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        return context


class ClientDetailView(StaffRequiredMixin, DetailView):
    """Отображает детальную информацию о клиенте."""
    model = Client
    template_name = 'clients/client_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 1. Передаем форму для модального окна
        context['payment_form'] = PaymentForm()

        # 2. Передаем ПОЛНЫЙ словарь с ценами
        price_map = {
            'work_service': "1800.00",
            'study_service': "1400.00",
            'consultation': "150.00",
            'document_preparation': "500.00",
            'full_service': "1200.00",
            'deposit': "300.00",
            'other': '0.00'
        }
        context['service_prices_json'] = json.dumps(price_map)

        # 3. Передаем чеклист документов
        client = self.get_object()
        if hasattr(client, 'get_document_checklist'):
            context['document_status_list'] = client.get_document_checklist()

        return context


class ClientCreateView(StaffRequiredMixin, CreateView):
    """Форма для создания нового клиента."""
    model = Client
    form_class = ClientForm
    template_name = "clients/client_form.html"
    success_url = reverse_lazy("clients:client_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Добавить нового клиента'
        return context

    def form_valid(self, form):
        messages.success(self.request, "Клиент успешно создан!")
        return super().form_valid(form)


class ClientUpdateView(StaffRequiredMixin, UpdateView):
    """Форма для редактирования данных существующего клиента."""
    model = Client
    form_class = ClientForm
    template_name = "clients/client_edit.html"

    def get_success_url(self):
        # После редактирования возвращаем на страницу деталей этого же клиента
        return reverse_lazy('clients:client_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Редактировать данные клиента'
        return context

    def form_valid(self, form):
        messages.success(self.request, "Данные клиента успешно обновлены!")
        return super().form_valid(form)


class ClientDeleteView(StaffRequiredMixin, DeleteView):
    """Страница подтверждения удаления клиента."""
    model = Client
    template_name = "clients/client_confirm_delete.html"
    success_url = reverse_lazy("clients:client_list")
    context_object_name = "client"

    def form_valid(self, form):
        client_name = self.get_object()
        messages.success(self.request, f"Клиент {client_name} был успешно удалён.")
        return super().form_valid(form)


@login_required
def dashboard_redirect(request):
    """Перенаправляет пользователя на соответствующую страницу после входа."""
    if request.user.is_staff:
        return redirect('clients:client_list')
    else:
        return redirect('portal:profile_detail')


@login_required
def update_client_notes(request, pk):
    """Обновляет заметки для клиента (только для сотрудников)."""
    if request.method == 'POST' and request.user.is_staff:
        client = get_object_or_404(Client, pk=pk)
        client.notes = request.POST.get('notes', '')
        client.save()
        messages.success(request, f"Заметка для клиента {client.first_name} сохранена.")
    return redirect('clients:client_detail', pk=pk)


@login_required
def add_document(request, client_id, doc_type):
    """Форма для добавления нового документа клиенту."""
    if not request.user.is_staff:
        return redirect('portal:profile_detail')

    client = get_object_or_404(Client, pk=client_id)
    # Получаем человеко-читаемое название документа
    document_type_display = client.get_document_name_by_code(doc_type)

    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.client = client
            document.document_type = doc_type
            document.save()
            messages.success(request, f"Документ '{document_type_display}' успешно добавлен.")
            return redirect('clients:client_detail', pk=client.id)
    else:
        form = DocumentUploadForm()

    return render(request, 'clients/add_document.html', {
        'form': form,
        'client': client,
        'document_type_display': document_type_display
    })


@login_required
def document_delete(request, pk):
    """Удаляет документ (POST-запросом)."""
    if not request.user.is_staff:
        return redirect('portal:profile_detail')

    document = get_object_or_404(Document, pk=pk)
    client_id = document.client.id
    doc_type_display = document.get_document_type_display()

    if request.method == "POST":
        document.delete()
        messages.success(request, f"Документ '{doc_type_display}' успешно удалён.")

    return redirect('clients:client_detail', pk=client_id)


@login_required
def toggle_document_verification(request, doc_id):
    """Переключает статус верификации документа."""
    if not request.user.is_staff:
        return redirect('portal:profile_detail')

    document = get_object_or_404(Document, pk=doc_id)
    if request.method == 'POST':
        document.verified = not document.verified
        document.save()
        status = "проверен" if document.verified else "не проверен"
        messages.success(request, f"Статус документа '{document.get_document_type_display()}' изменен на '{status}'.")

    return redirect('clients:client_detail', pk=document.client.id)


# --- Платежи ---
@login_required
def add_payment(request, client_id):
    if not request.user.is_staff:
        return redirect('portal:profile_detail')

    client = get_object_or_404(Client, pk=client_id)
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.client = client
            payment.save()
            messages.success(request, "Платёж успешно добавлен.")
        else:
            # Если форма невалидна, выводим ошибки
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"Ошибка в поле '{form.fields[field].label}': {error}")

    return redirect('clients:client_detail', pk=client.id)


@login_required
def edit_payment(request, payment_id):
    if not request.user.is_staff:
        return redirect('portal:profile_detail')

    payment = get_object_or_404(Payment, pk=payment_id)
    client_id = payment.client.id
    if request.method == 'POST':
        form = PaymentForm(request.POST, instance=payment)
        if form.is_valid():
            form.save()
            messages.success(request, "Платёж успешно обновлён.")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"Ошибка в поле '{form.fields[field].label}': {error}")

    return redirect('clients:client_detail', pk=client_id)


@login_required
def delete_payment(request, payment_id):
    if not request.user.is_staff:
        return redirect('portal:profile_detail')

    payment = get_object_or_404(Payment, pk=payment_id)
    client_id = payment.client.id
    if request.method == 'POST':
        payment.delete()
        messages.success(request, f"Платёж '{payment.get_service_description_display()}' успешно удалён.")

    return redirect('clients:client_detail', pk=client_id)


# --- Напоминания ---
@login_required
def reminder_list(request):
    if not request.user.is_staff:
        return redirect('portal:profile_detail')
    reminders = Reminder.objects.filter(is_active=True, due_date__gte=timezone.now().date()).order_by('due_date')
    return render(request, 'clients/reminder_list.html', {'reminders': reminders})


@login_required
def run_create_reminders(request):
    if not request.user.is_staff:
        return redirect('portal:profile_detail')
    try:
        call_command('create_reminders')
        messages.success(request, "Проверка завершена, новые напоминания успешно созданы!")
    except Exception as e:
        messages.error(request, f"Произошла ошибка при создании напоминаний: {e}")
    return redirect('clients:reminder_list')


@login_required
def delete_reminder(request, reminder_id):
    if not request.user.is_staff:
        return redirect('portal:profile_detail')

    reminder = get_object_or_404(Reminder, pk=reminder_id)
    if request.method == 'POST':
        reminder_title = reminder.title
        reminder.delete()
        messages.success(request, f"Напоминание '{reminder_title}' успешно удалено.")
    return redirect('clients:reminder_list')


# --- Инструменты ---
@login_required
def calculator_view(request):
    """Отображает и обрабатывает калькулятор для выписки из банка."""
    if not request.user.is_staff:
        return redirect('portal:profile_detail')

    LIVING_ALLOWANCE = 1010
    TICKET_BORDER = 500
    TICKET_NO_BORDER = 2500
    MAX_MONTHS_LIVING = 15
    EUR_TO_PLN_RATE = 4.3

    context = {
        'living_allowance': LIVING_ALLOWANCE,
        'eur_to_pln_rate': EUR_TO_PLN_RATE,
        'max_months_living': MAX_MONTHS_LIVING
    }

    if request.method == 'POST':
        try:
            # Сбор и обработка данных из формы
            tuition_fee = float(request.POST.get('tuition_fee', 0))
            if request.POST.get('tuition_currency') == 'EUR':
                tuition_fee *= EUR_TO_PLN_RATE

            months_in_period = int(request.POST.get('months_in_period', 1))
            monthly_tuition = tuition_fee / months_in_period if months_in_period > 0 else 0

            monthly_rent_and_bills = float(request.POST.get('rent_and_bills', 0))
            if request.POST.get('rent_currency') == 'EUR':
                monthly_rent_and_bills *= EUR_TO_PLN_RATE

            num_people = int(request.POST.get('num_people', 1))
            rent_per_person = monthly_rent_and_bills / num_people if num_people > 0 else 0

            total_end_date_str = request.POST.get('total_end_date')
            total_end_date = datetime.strptime(total_end_date_str, '%d-%m-%Y')
            now = datetime.now()

            # --- ИСПРАВЛЕНА ЛОГИКА РАСЧЁТА МЕСЯЦЕВ ---
            # Корректно считаем количество календарных месяцев, которые покрывает период.
            # Например, с 18 июля по 5 августа - это 2 месяца (июль и август).
            if total_end_date < now:
                # Если дата в прошлом, считаем как 1 месяц, чтобы избежать отрицательных значений
                total_months_real = 1
            else:
                year_diff = total_end_date.year - now.year
                month_diff = total_end_date.month - now.month
                total_months_real = year_diff * 12 + month_diff + 1

            # Гарантируем, что для расчёта используется минимум 1 месяц.
            if total_months_real <= 0:
                total_months_real = 1

            months_for_calc = min(total_months_real, MAX_MONTHS_LIVING)

            # --- Логика билета ---
            has_border = request.POST.get('has_border') == 'on'
            return_ticket = TICKET_BORDER if has_border else TICKET_NO_BORDER

            total_monthly_costs = rent_per_person + monthly_tuition + LIVING_ALLOWANCE
            total_base_cost = total_monthly_costs * months_for_calc
            final_total_required = total_base_cost + return_ticket

            context['results'] = {
                'rent_per_person': f"{rent_per_person:,.2f}".replace(",", " "),
                'monthly_tuition_calculated': f"{monthly_tuition:,.2f}".replace(",", " "),
                'total_monthly_costs': f"{total_monthly_costs:,.2f}".replace(",", " "),
                'months_for_calc': months_for_calc,
                'total_base_cost': f"{total_base_cost:,.2f}".replace(",", " "),
                'return_ticket': f"{return_ticket:,.2f}".replace(",", " "),
                'final_total_required': f"{final_total_required:,.2f}".replace(",", " "),
            }
            context['form_data'] = request.POST

        except (ValueError, TypeError, AttributeError) as e:
            messages.error(request,
                           f"Ошибка в калькуляторе. Пожалуйста, заполните все поля корректными значениями. (Системная ошибка: {e})")

    return render(request, 'clients/calculator.html', context)


@login_required
def client_print_view(request, pk):
    """Генерирует страницу с данными клиента для печати."""
    if not request.user.is_staff:
        return redirect('portal:profile_detail')

    client = get_object_or_404(Client, pk=pk)
    return render(request, 'clients/client_printable.html', {'client': client})