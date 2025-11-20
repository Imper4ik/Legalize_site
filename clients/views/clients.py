from __future__ import annotations

from datetime import datetime

from django.contrib import messages
from django.db.models import Prefetch, Q
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView
from django.conf import settings

from clients.forms import ClientForm, PaymentForm
from clients.models import Client, Document, Payment
from clients.views.base import StaffRequiredMixin
from clients.services.responses import apply_no_store


class ClientListView(StaffRequiredMixin, ListView):
    model = Client
    template_name = 'clients/clients_list.html'
    context_object_name = 'clients'
    paginate_by = 15

    def get_queryset(self):
        queryset = Client.objects.filter(Q(user__is_staff=False) | Q(user__isnull=True))
        query = self.request.GET.get('q', '')
        if query:
            return queryset.filter(
                Q(first_name__icontains=query) | Q(last_name__icontains=query) |
                Q(email__icontains=query) | Q(phone__icontains=query) | Q(case_number__icontains=query)
            ).distinct().order_by('-created_at')
        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        return context


class ClientDetailView(StaffRequiredMixin, DetailView):
    model = Client
    template_name = 'clients/client_detail.html'

    def get_queryset(self):
        return (
            Client.objects.select_related('user')
            .prefetch_related(
                Prefetch('payments', queryset=Payment.objects.order_by('-created_at')),
                Prefetch('documents', queryset=Document.objects.order_by('-uploaded_at')),
                'reminders',
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.object
        context['payment_form'] = PaymentForm()
        if hasattr(client, 'get_document_checklist'):
            context['document_status_list'] = client.get_document_checklist()
        return context


class ClientCreateView(StaffRequiredMixin, CreateView):
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

    def form_invalid(self, form):
        messages.error(
            self.request,
            "Не удалось сохранить клиента. Проверьте выделенные поля и попробуйте снова.",
        )
        return super().form_invalid(form)


class ClientUpdateView(StaffRequiredMixin, UpdateView):
    model = Client
    form_class = ClientForm
    template_name = "clients/client_form.html"

    def get_success_url(self):
        return reverse_lazy('clients:client_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Редактировать данные клиента'
        return context

    def form_valid(self, form):
        messages.success(self.request, "Данные клиента успешно обновлены!")
        return super().form_valid(form)


class ClientDeleteView(StaffRequiredMixin, DeleteView):
    model = Client
    template_name = "clients/client_confirm_delete.html"
    success_url = reverse_lazy("clients:client_list")

    def form_valid(self, form):
        client_name = self.get_object()
        messages.success(self.request, f"Клиент {client_name} был успешно удалён.")
        return super().form_valid(form)


def dashboard_redirect_view(request):
    """
    Перенаправляет пользователя в зависимости от его статуса.
    Сотрудников - на список клиентов, клиентов - на их профиль.
    """
    if request.user.is_staff:
        return redirect('clients:client_list')

    support_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'support@example.com')
    context = {
        'support_email': support_email,
        'error_title': _('Доступ запрещен'),
    }
    return render(request, '403.html', context=context, status=403)


# --- Инструменты ---

def calculator_view(request):
    """Отображает и обрабатывает калькулятор для выписки из банка."""

    # Константы для расчетов
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
            # --- Сбор данных из формы ---
            tuition_fee_pln = float(request.POST.get('tuition_fee', 0))
            if request.POST.get('tuition_currency') == 'EUR':
                tuition_fee_pln *= EUR_TO_PLN_RATE

            months_in_period = int(request.POST.get('months_in_period', 1))
            months_in_period = max(months_in_period, 1)
            monthly_tuition = tuition_fee_pln
            tuition_total = monthly_tuition * months_in_period

            monthly_rent_and_bills = float(request.POST.get('rent_and_bills', 0))
            if request.POST.get('rent_currency') == 'EUR':
                monthly_rent_and_bills *= EUR_TO_PLN_RATE

            num_people = int(request.POST.get('num_people', 1))
            rent_per_person = monthly_rent_and_bills / num_people if num_people > 0 else 0

            total_end_date_str = request.POST.get('total_end_date')
            total_end_date = datetime.strptime(total_end_date_str, '%d-%m-%Y')
            now = datetime.now()

            if total_end_date < now:
                total_months_real = 1
            else:
                year_diff = total_end_date.year - now.year
                month_diff = total_end_date.month - now.month
                total_months_real = year_diff * 12 + month_diff + 1
            if total_months_real <= 0:
                total_months_real = 1

            months_for_calc = min(total_months_real, MAX_MONTHS_LIVING)
            is_capped = total_months_real > MAX_MONTHS_LIVING

            has_border = request.POST.get('has_border') == 'on'
            return_ticket = TICKET_BORDER if has_border else TICKET_NO_BORDER

            # --- Финальные расчеты ---
            total_monthly_costs = rent_per_person + monthly_tuition + LIVING_ALLOWANCE
            total_base_cost = total_monthly_costs * months_for_calc
            final_total_required = total_base_cost + return_ticket

            context['results'] = {
                'rent_total': f"{monthly_rent_and_bills:,.2f}".replace(",", " "),
                'num_people': num_people,
                'rent_per_person': f"{rent_per_person:,.2f}".replace(",", " "),

                'tuition_total': f"{tuition_total:,.2f}".replace(",", " "),
                'months_in_period': months_in_period,
                'monthly_tuition_calculated': f"{monthly_tuition:,.2f}".replace(",", " "),

                'total_monthly_costs': f"{total_monthly_costs:,.2f}".replace(",", " "),

                'total_months_real': total_months_real,
                'months_for_calc': months_for_calc,
                'is_capped': is_capped,

                'total_base_cost': f"{total_base_cost:,.2f}".replace(",", " "),
                'return_ticket': f"{return_ticket:,.2f}".replace(",", " "),
                'final_total_required': f"{final_total_required:,.2f}".replace(",", " "),
            }
            context['form_data'] = request.POST

        except (ValueError, TypeError, AttributeError) as e:
            messages.error(request,
                           f"Ошибка. Пожалуйста, заполните все поля корректными значениями. (Системная ошибка: {e})")

    response = render(request, 'clients/calculator.html', context)
    return apply_no_store(response)


class ClientPrintBaseView(StaffRequiredMixin, DetailView):
    """Базовое представление для печати данных клиента."""

    model = Client
    context_object_name = 'client'


class ClientPrintView(ClientPrintBaseView):
    template_name = 'clients/client_printable.html'


class ClientWSCPrintView(ClientPrintBaseView):
    template_name = 'clients/client_wsc_print.html'


# Функции-обёртки сохраняют прежние точки входа, чтобы не переписывать URLConf
client_print_view = ClientPrintView.as_view()
client_wsc_print_view = ClientWSCPrintView.as_view()
