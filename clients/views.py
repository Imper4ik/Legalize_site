# clients/views.py (ФИНАЛЬНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ)

from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q, Prefetch
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.core.management import call_command
from datetime import datetime
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.conf import settings
from functools import wraps

from legalize_site.utils.http import request_is_ajax
from .models import Client, Document, Payment, Reminder
from .forms import ClientForm, DocumentUploadForm, PaymentForm


def json_no_store(payload, *, status=200):
    response = JsonResponse(payload, status=status)
    response['Cache-Control'] = 'no-store'
    return response


def staff_required_view(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            message = _('Доступ запрещен')
            if request_is_ajax(request):
                return json_no_store({'status': 'error', 'message': message}, status=403)
            return HttpResponseForbidden(message)
        return view_func(request, *args, **kwargs)

    return _wrapped


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


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


@login_required
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


@login_required
@staff_required_view
def update_client_notes(request, pk):
    client = get_object_or_404(Client, pk=pk)
    expects_json = request_is_ajax(request)

    if request.method == 'POST':
        client.notes = request.POST.get('notes', '')
        client.save()
        if expects_json:
            return json_no_store({'status': 'success', 'message': 'Заметка сохранена'})
        messages.success(request, "Заметка сохранена.")
        return redirect('clients:client_detail', pk=pk)
    return redirect('clients:client_list')


@login_required
@staff_required_view
def add_document(request, client_id, doc_type):
    client = get_object_or_404(Client, pk=client_id)
    document_type_display = client.get_document_name_by_code(doc_type)
    expects_json = request_is_ajax(request)

    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.client = client
            document.document_type = doc_type
            document.save()

            # Если это AJAX-запрос, отправляем JSON
            if expects_json:
                return json_no_store({
                    'status': 'success',
                    'message': f"Документ '{document_type_display}' успешно добавлен.",
                    'doc_id': document.id
                })

            # Если это обычный запрос, оставляем как было
            messages.success(request, f"Документ '{document_type_display}' успешно добавлен.")
            return redirect('clients:client_detail', pk=client.id)
        else:
            if expects_json:
                return json_no_store({
                    'status': 'error',
                    'errors': form.errors,
                    'message': 'Проверьте правильность заполнения формы.'
                }, status=400)

    # Для GET-запроса ничего не меняем
    form = DocumentUploadForm()
    return render(request, 'clients/add_document.html', {
        'form': form, 'client': client, 'document_type_display': document_type_display
    })


@login_required
@staff_required_view
def document_delete(request, pk):
    document = get_object_or_404(Document, pk=pk)
    client_id = document.client.id
    expects_json = request_is_ajax(request)

    if request.method == "POST":
        doc_type_display = document.get_document_type_display()
        document.delete()  # Сигнал позаботится об удалении файла

        if expects_json:
            return json_no_store({'status': 'success', 'message': f"Документ '{doc_type_display}' удалён."})

        messages.success(request, f"Документ '{doc_type_display}' успешно удалён.")
    else:
        messages.warning(request, "Удаление возможно только через кнопку.")

    return redirect('clients:client_detail', pk=client_id)


@login_required
@staff_required_view
def toggle_document_verification(request, doc_id):
    """
    Переключает статус верификации документа. Поддерживает AJAX.
    """
    document = get_object_or_404(Document, pk=doc_id)
    expects_json = request_is_ajax(request)
    if request.method == 'POST':
        document.verified = not document.verified
        document.save()

        # Если это AJAX-запрос, отправляем JSON-ответ
        if expects_json:
            return json_no_store({
                'status': 'success',
                'verified': document.verified,
                'button_text': "Снять отметку" if document.verified else "Проверить"
            })

        status = "проверен" if document.verified else "не проверен"
        messages.success(request, f"Статус документа изменен на '{status}'.")
    return redirect('clients:client_detail', pk=document.client.id)


@login_required
@staff_required_view
def add_payment(request, client_id):
    client = get_object_or_404(Client, pk=client_id)
    expects_json = request_is_ajax(request)
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.client = client
            payment.save()
            if expects_json:
                html = render_to_string('clients/partials/payment_item.html', {'payment': payment})
                return json_no_store({'status': 'success', 'html': html, 'payment_id': payment.id})
            messages.success(request, "Платёж успешно добавлен.")
            return redirect('clients:client_detail', pk=client.id)
        else:
            if expects_json:
                return json_no_store({
                    'status': 'error',
                    'errors': form.errors,
                    'message': 'Проверьте правильность заполнения формы.'
                }, status=400)

    return redirect('clients:client_detail', pk=client.id)


@login_required
@staff_required_view
def edit_payment(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    expects_json = request_is_ajax(request)
    if request.method == 'POST':
        form = PaymentForm(request.POST, instance=payment)
        if form.is_valid():
            payment = form.save()
            if expects_json:
                html = render_to_string('clients/partials/payment_item.html', {'payment': payment})
                return json_no_store({'status': 'success', 'html': html, 'payment_id': payment.id})
            messages.success(request, "Платёж успешно обновлён.")
            return redirect('clients:client_detail', pk=payment.client.id)
        else:
            if expects_json:
                return json_no_store({
                    'status': 'error',
                    'errors': form.errors,
                    'message': 'Проверьте правильность заполнения формы.'
                }, status=400)

    return redirect('clients:client_detail', pk=payment.client.id)


@login_required
@staff_required_view
def delete_payment(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    client_id = payment.client.id
    expects_json = request_is_ajax(request)
    if request.method == 'POST':
        payment.delete()
        if expects_json:
            return json_no_store({'status': 'success'})
        messages.success(request, "Платёж успешно удалён.")
    return redirect('clients:client_detail', pk=client_id)


# --- Инструменты ---
@login_required
@staff_required_view
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
            if total_months_real <= 0: total_months_real = 1

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

    return render(request, 'clients/calculator.html', context)


class ClientPrintBaseView(StaffRequiredMixin, DetailView):
    """Базовое представление для печатных форм клиента."""

    model = Client
    context_object_name = 'client'


class ClientPrintView(ClientPrintBaseView):
    template_name = 'clients/client_printable.html'


class ClientWSCPrintView(ClientPrintBaseView):
    template_name = 'clients/client_wsc_print.html'


# Функции-обёртки сохраняют прежние точки входа, чтобы не переписывать URLConf
client_print_view = ClientPrintView.as_view()
client_wsc_print_view = ClientWSCPrintView.as_view()


@login_required
@staff_required_view
def client_status_api(request, pk):
    """Возвращает актуальный чеклист клиента в формате JSON для 'живого' обновления."""
    client = get_object_or_404(Client, pk=pk)

    checklist_html = render_to_string('clients/partials/document_checklist.html', {
        'document_status_list': client.get_document_checklist(),
        'client': client
    })
    return json_no_store({'status': 'success', 'checklist_html': checklist_html})


@login_required
@staff_required_view
def client_overview_partial(request, pk):
    """Возвращает HTML со сводной информацией о клиенте для автообновления на странице сотрудника."""

    client = get_object_or_404(Client, pk=pk)
    overview_html = render_to_string('clients/partials/client_overview.html', {'client': client}, request=request)
    return json_no_store({'status': 'success', 'html': overview_html})


# --- НАПОМИНАНИЯ (REMindERS) ---


class ReminderListView(StaffRequiredMixin, ListView):
    model = Reminder
    context_object_name = 'reminders'
    reminder_type = None
    template_name = ''
    title = ''
    client_param = 'client'
    start_date_param = 'start_date'
    end_date_param = 'end_date'

    def get_queryset(self):
        queryset = (
            Reminder.objects.filter(is_active=True, reminder_type=self.reminder_type)
            .select_related('client')
            .order_by('due_date')
        )

        start_date = self.request.GET.get(self.start_date_param, '')
        if start_date:
            queryset = queryset.filter(due_date__gte=start_date)

        end_date = self.request.GET.get(self.end_date_param, '')
        if end_date:
            queryset = queryset.filter(due_date__lte=end_date)

        client_value = self.request.GET.get(self.client_param, '')
        self.client_filter_id = None
        if client_value.isdigit():
            self.client_filter_id = int(client_value)
            queryset = queryset.filter(client_id=self.client_filter_id)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        reminders = context['reminders']
        context.update(
            {
                'title': self.title,
                'all_clients': Client.objects.filter(user__is_staff=False).order_by('last_name', 'first_name'),
                'filter_values': self.request.GET,
                'client_filter_id': getattr(self, 'client_filter_id', None),
                'reminders_count': reminders.count() if hasattr(reminders, 'count') else len(reminders),
            }
        )
        return context


class DocumentReminderListView(ReminderListView):
    reminder_type = 'document'
    template_name = 'clients/document_reminder_list.html'
    title = _('Напоминания по документам')
    client_param = 'doc_client'
    start_date_param = 'doc_start_date'
    end_date_param = 'doc_end_date'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_reminders_count'] = context['reminders_count']
        return context


class PaymentReminderListView(ReminderListView):
    reminder_type = 'payment'
    template_name = 'clients/payment_reminder_list.html'
    title = _('Напоминания по оплатам')


@login_required
@staff_required_view
def run_update_reminders(request):
    if request.method == 'POST':
        try:
            call_command('update_reminders')
            messages.success(request, "Проверка завершена. Новые напоминания, если были найдены, успешно созданы!")
        except Exception as e:
            messages.error(request, f"Произошла ошибка при создании напоминаний: {e}")
        next_page = request.POST.get('next', 'documents')
        if next_page == 'payments':
            return redirect('clients:payment_reminder_list')
        else:
            return redirect('clients:document_reminder_list')
    else:
        messages.warning(request, "Эту операцию можно выполнить только через специальную кнопку.")
        return redirect('clients:document_reminder_list')


@login_required
@staff_required_view
def reminder_action(request, reminder_id):
    reminder = get_object_or_404(Reminder, pk=reminder_id)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'delete':
            reminder.delete()
        elif action == 'deactivate':
            reminder.is_active = False
            reminder.save()
    return redirect('clients:document_reminder_list')


@login_required
@staff_required_view
def client_checklist_partial(request, pk):
    client = get_object_or_404(Client, pk=pk)
    document_status_list = client.get_document_checklist()
    response = render(request, 'clients/partials/document_checklist.html', {
        'client': client,
        'document_status_list': document_status_list
    })
    response['Cache-Control'] = 'no-store'
    return response


@login_required
@staff_required_view
def get_price_for_service(request, service_value):
    prices = {
        'study_service': 1400.00,
        'work_service': 1800.00,
        'consultation': 180.00,
    }
    # Находим цену по ключу. Если ключа нет, вернется 0.00
    price = prices.get(service_value, 0.00)
    return json_no_store({'price': price})
