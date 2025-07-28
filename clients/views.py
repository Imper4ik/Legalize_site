# -*- coding: utf-8 -*-
import json
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.core.management import call_command
from datetime import datetime, timezone
from django.template.loader import render_to_string

# ... (Импорты ваших моделей и форм)
from .models import Client, Document, Payment, Reminder
from .forms import ClientForm, DocumentUploadForm, PaymentForm


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


class ClientListView(StaffRequiredMixin, ListView):
    model = Client
    template_name = 'clients/clients_list.html'
    context_object_name = 'clients'
    paginate_by = 15

    def get_queryset(self):
        # Сначала получаем базовый список, ИСКЛЮЧАЯ всех сотрудников и админов
        queryset = Client.objects.filter(user__is_staff=False)

        # Затем применяем логику поиска, если есть поисковый запрос
        query = self.request.GET.get('q', '')
        if query:
            return queryset.filter(
                Q(first_name__icontains=query) | Q(last_name__icontains=query) |
                Q(email__icontains=query) | Q(phone__icontains=query) | Q(case_number__icontains=query)
            ).distinct().order_by('-created_at')

        # Если поиска нет, возвращаем отфильтрованный список
        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        return context


class ClientDetailView(StaffRequiredMixin, DetailView):
    model = Client
    template_name = 'clients/client_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.get_object()
        context['payment_form'] = PaymentForm()
        price_map = {
            'work_service': "1800.00", 'study_service': "1400.00", 'consultation': "150.00",
            'document_preparation': "500.00", 'full_service': "1200.00", 'deposit': "300.00", 'other': '0.00'
        }
        context['service_prices_json'] = json.dumps(price_map)
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
def dashboard_redirect(request):
    if request.user.is_staff:
        return redirect('clients:client_list')
    return redirect('portal:profile_detail')


@login_required
def update_client_notes(request, pk):
    if not request.user.is_staff:
        return JsonResponse({'status': 'error', 'message': 'Доступ запрещен'}, status=403)
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        client.notes = request.POST.get('notes', '')
        client.save()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success', 'message': 'Заметка сохранена'})
        messages.success(request, "Заметка сохранена.")
        return redirect('clients:client_detail', pk=pk)
    return redirect('clients:client_list')


@login_required
def add_document(request, client_id, doc_type):
    # Эта проверка доступа для персонала должна быть в начале
    if not request.user.is_staff:
        # Для AJAX возвращаем ошибку, иначе - редирект
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Доступ запрещен'}, status=403)
        return redirect('portal:profile_detail')

    client = get_object_or_404(Client, pk=client_id)
    document_type_display = client.get_document_name_by_code(doc_type)

    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.client = client
            document.document_type = doc_type
            document.save()

            # --- НАЧАЛО ИЗМЕНЕНИЙ ---
            # Если это AJAX-запрос, отправляем JSON
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                # Вы можете отправить любой полезный JSON, например, ID документа
                return JsonResponse({
                    'status': 'success',
                    'message': f"Документ '{document_type_display}' успешно добавлен.",
                    'doc_id': document.id
                })

            # Если это обычный запрос, оставляем как было
            messages.success(request, f"Документ '{document_type_display}' успешно добавлен.")
            return redirect('clients:client_detail', pk=client.id)
            # --- КОНЕЦ ИЗМЕНЕНИЙ ---
        else:
            # Также хорошая практика - возвращать ошибки формы для AJAX
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)

    # Для GET-запроса ничего не меняем
    form = DocumentUploadForm()
    return render(request, 'clients/add_document.html', {
        'form': form, 'client': client, 'document_type_display': document_type_display
    })


@login_required
def document_delete(request, pk):
    if not request.user.is_staff:
        # Для AJAX возвращаем JSON, иначе - редирект
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Доступ запрещен'}, status=403)
        return redirect('portal:profile_detail')

    document = get_object_or_404(Document, pk=pk)
    client_id = document.client.id

    if request.method == "POST":
        doc_type_display = document.get_document_type_display()
        document.delete()  # Сигнал позаботится об удалении файла

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success', 'message': f"Документ '{doc_type_display}' удалён."})

        messages.success(request, f"Документ '{doc_type_display}' успешно удалён.")
    else:
        messages.warning(request, "Удаление возможно только через кнопку.")

    return redirect('clients:client_detail', pk=client_id)


@login_required
def toggle_document_verification(request, doc_id):
    """
    Переключает статус верификации документа. Поддерживает AJAX.
    """
    if not request.user.is_staff:
        return JsonResponse({'status': 'error', 'message': 'Доступ запрещен'}, status=403)

    document = get_object_or_404(Document, pk=doc_id)
    if request.method == 'POST':
        document.verified = not document.verified
        document.save()

        # Если это AJAX-запрос, отправляем JSON-ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'success',
                'verified': document.verified,
                'button_text': "Снять отметку" if document.verified else "Проверить"
            })

        status = "проверен" if document.verified else "не проверен"
        messages.success(request, f"Статус документа изменен на '{status}'.")
    return redirect('clients:client_detail', pk=document.client.id)


@login_required
def add_payment(request, client_id):
    if not request.user.is_staff:
        return JsonResponse({'status': 'error', 'message': 'Доступ запрещен'}, status=403)

    client = get_object_or_404(Client, pk=client_id)
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.client = client
            payment.save()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                html = render_to_string('clients/partials/payment_item.html', {'payment': payment})
                return JsonResponse({'status': 'success', 'html': html, 'payment_id': payment.id})
            messages.success(request, "Платёж успешно добавлен.")
            return redirect('clients:client_detail', pk=client.id)
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)

    return redirect('clients:client_detail', pk=client.id)


@login_required
def edit_payment(request, payment_id):
    if not request.user.is_staff:
        return JsonResponse({'status': 'error', 'message': 'Доступ запрещен'}, status=403)

    payment = get_object_or_404(Payment, pk=payment_id)
    if request.method == 'POST':
        form = PaymentForm(request.POST, instance=payment)
        if form.is_valid():
            payment = form.save()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                html = render_to_string('clients/partials/payment_item.html', {'payment': payment})
                return JsonResponse({'status': 'success', 'html': html, 'payment_id': payment.id})
            messages.success(request, "Платёж успешно обновлён.")
            return redirect('clients:client_detail', pk=payment.client.id)
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)

    return redirect('clients:client_detail', pk=payment.client.id)


@login_required
def delete_payment(request, payment_id):
    if not request.user.is_staff:
        return JsonResponse({'status': 'error', 'message': 'Доступ запрещен'}, status=403)

    payment = get_object_or_404(Payment, pk=payment_id)
    client_id = payment.client.id
    if request.method == 'POST':
        payment.delete()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success'})
        messages.success(request, "Платёж успешно удалён.")
    return redirect('clients:client_detail', pk=client_id)


# --- Инструменты ---
@login_required
def calculator_view(request):
    """Отображает и обрабатывает калькулятор для выписки из банка."""
    if not request.user.is_staff:
        return redirect('portal:profile_detail')

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

            # --- Более точный расчет месяцев ---
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

            # --- НОВЫЙ, БОЛЕЕ ПОДРОБНЫЙ КОНТЕКСТ ДЛЯ ШАБЛОНА ---
            context['results'] = {
                'rent_total': f"{monthly_rent_and_bills:,.2f}".replace(",", " "),
                'num_people': num_people,
                'rent_per_person': f"{rent_per_person:,.2f}".replace(",", " "),

                'tuition_total': f"{tuition_fee:,.2f}".replace(",", " "),
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


@login_required
def client_print_view(request, pk):
    """Генерирует страницу с данными клиента для печати."""
    if not request.user.is_staff:
        return redirect('portal:profile_detail')

    client = get_object_or_404(Client, pk=pk)
    return render(request, 'clients/client_printable.html', {'client': client})


@login_required
def grant_checklist_access(request, pk):
    """
    Предоставляет клиенту доступ к чеклисту документов.
    """
    if not request.user.is_staff:
        return redirect('portal:profile_detail')

    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        client.has_checklist_access = True
        client.save()
        messages.success(request, f"Доступ к документам для клиента {client} успешно предоставлен!")

    return redirect('clients:client_detail', pk=pk)


@login_required
def grant_checklist_access(request, pk):
    """Предоставляет клиенту доступ к чеклисту. Поддерживает AJAX."""
    if not request.user.is_staff:
        return JsonResponse({'status': 'error', 'message': 'Доступ запрещен'}, status=403)

    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        client.has_checklist_access = True
        client.save()

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            # Отрендерим обновленный блок и вернем его как HTML
            html = render_to_string('clients/partials/access_management_block.html', {'client': client})
            return JsonResponse({'status': 'success', 'html': html})

        messages.success(request, f"Доступ для клиента {client} предоставлен!")
    return redirect('clients:client_detail', pk=pk)


@login_required
def client_status_api(request, pk):
    """Возвращает актуальный чеклист клиента в формате JSON для 'живого' обновления."""
    client = get_object_or_404(Client, pk=pk)
    # Проверка, что только сотрудник может запрашивать эти данные
    if not request.user.is_staff:
        return JsonResponse({'status': 'error', 'message': 'Доступ запрещен'}, status=403)

    checklist_html = render_to_string('clients/partials/document_checklist.html', {
        'document_status_list': client.get_document_checklist(),
        'client': client
    })
    return JsonResponse({'status': 'success', 'checklist_html': checklist_html})


# --- НАПОМИНАНИЯ (REMindERS) ---
# Эта секция была улучшена

@login_required
def reminder_list_redirect(request):
    """
    НОВАЯ ФУНКЦИЯ: Перенаправляет старую ссылку на напоминания
    на новую страницу с напоминаниями по документам.
    Это исправляет ошибку в навигационном меню.
    """
    return redirect('clients:document_reminder_list')


@login_required
def document_reminder_list(request):
    if not request.user.is_staff:
        return redirect('portal:profile_detail')

    # --- ИЗМЕНЕННАЯ ЛОГИКА ---
    # 1. Базовый запрос: выбираем все активные напоминания по документам.
    base_query = Reminder.objects.filter(is_active=True, reminder_type='document').select_related('client')

    # 2. Получаем фильтры из GET-запроса.
    doc_client_filter = request.GET.get('doc_client', '')
    doc_start_date_filter = request.GET.get('doc_start_date', '')
    doc_end_date_filter = request.GET.get('doc_end_date', '')

    # 3. Если пользователь НЕ использовал фильтры дат, показываем все просроченные напоминания.
    if not doc_start_date_filter and not doc_end_date_filter:
        today = timezone.now().date()
        # Показываем все, что уже просрочено
        document_query = base_query.filter(due_date__lte=today).order_by('due_date')
    else:
        # Если фильтры есть, применяем их как раньше.
        document_query = base_query.order_by('due_date')
        if doc_start_date_filter:
            try:
                start_date = datetime.datetime.strptime(doc_start_date_filter, '%Y-%m-%d').date()
                document_query = document_query.filter(due_date__gte=start_date)
            except ValueError:
                messages.error(request, "Неверный формат начальной даты для документов.")
        if doc_end_date_filter:
            try:
                end_date = datetime.datetime.strptime(doc_end_date_filter, '%Y-%m-%d').date()
                document_query = document_query.filter(due_date__lte=end_date)
            except ValueError:
                messages.error(request, "Неверный формат конечной даты для документов.")

    # Применяем фильтр по клиенту в любом случае
    doc_client_filter_id = None
    if doc_client_filter.isdigit():
        doc_client_filter_id = int(doc_client_filter)
        document_query = document_query.filter(client_id=doc_client_filter_id)

    # --------------------------

    context = {
        'title': 'Напоминания по документам',
        'document_reminders': document_query,
        'total_reminders_count': document_query.count(),
        'all_clients': Client.objects.filter(user__is_staff=False).order_by('last_name', 'first_name'),
        'doc_filter_values': request.GET,
        'doc_client_filter_id': doc_client_filter_id,
    }

    return render(request, 'clients/document_reminder_list.html', context)


@login_required
def payment_reminder_list(request):
    """
    Отображает список активных напоминаний ТОЛЬКО ПО ОПЛАТАМ.
    """
    if not request.user.is_staff:
        return redirect('portal:profile_detail')

    query = Reminder.objects.filter(is_active=True, reminder_type='payment').select_related('client').order_by('due_date')

    # Обратите внимание: здесь используются 'client', 'start_date', 'end_date'
    # Убедитесь, что ваша HTML-форма для платежей использует именно эти имена!
    client_filter = request.GET.get('client', '')
    start_date_filter = request.GET.get('start_date', '')
    end_date_filter = request.GET.get('end_date', '')

    client_filter_id = None
    if client_filter.isdigit():
        client_filter_id = int(client_filter)
        query = query.filter(client_id=client_filter_id)
    if start_date_filter:
        query = query.filter(due_date__gte=start_date_filter)
    if end_date_filter:
        query = query.filter(due_date__lte=end_date_filter)

    context = {
        'title': 'Напоминания по оплатам',
        'reminders': query,
        'all_clients': Client.objects.all().order_by('last_name', 'first_name'),
        'filter_values': request.GET,
        'client_filter_id': client_filter_id,
    }
    return render(request, 'clients/payment_reminder_list.html', context)


@login_required
def run_update_reminders(request):
    if not request.user.is_staff:
        return redirect('portal:profile_detail')

    if request.method == 'POST':
        try:
            # print("Вызов команды update_reminders...") # Можно оставить для отладки
            call_command('update_reminders')
            messages.success(request, "Проверка завершена. Новые напоминания, если были найдены, успешно созданы!")
        except Exception as e:
            messages.error(request, f"Произошла ошибка при создании напоминаний: {e}")

        # --- ЭТОТ БЛОК ЛОГИКИ ОЧЕНЬ ВАЖЕН ---
        next_page = request.POST.get('next', 'documents') # Получаем значение из скрытого поля 'next'
                                                          # По умолчанию 'documents', если 'next' не передан

        if next_page == 'payments':
            return redirect('clients:payment_reminder_list')
        else: # Это покроет 'documents' и любые неожиданные значения
            return redirect('clients:document_reminder_list')
        # ------------------------------------

    else: # Если кто-то пытается зайти на этот URL методом GET
        messages.warning(request, "Эту операцию можно выполнить только через специальную кнопку.")
        return redirect('clients:document_reminder_list') # Перенаправляем на страницу документов


@login_required
def reminder_action(request, reminder_id):
    """
    Обрабатывает действия с напоминанием: деактивация или удаление.
    """
    if not request.user.is_staff:
        return redirect('portal:profile_detail')

    reminder = get_object_or_404(Reminder, pk=reminder_id)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'delete':
            reminder_title = reminder.title
            reminder.delete()
            messages.success(request, f"Напоминание '{reminder_title}' было безвозвратно удалено.")
        elif action == 'deactivate':
            reminder.is_active = False
            reminder.save()
            messages.success(request, f"Напоминание '{reminder.title}' было отмечено как выполненное.")

    # --- ИСПРАВЛЕНИЕ: Перенаправление на страницу напоминаний по документам ---
    # Это было предыдущее исправление, оставляем его, так как оно логично после действия над одним напоминанием
    return redirect('clients:document_reminder_list')


@login_required
def client_checklist_partial(request, pk):
    """
    Возвращает только HTML-фрагмент чеклиста документов.
    Используется для AJAX-обновления.
    """
    if not request.user.is_staff:
        return HttpResponseForbidden()

    client = get_object_or_404(Client, pk=pk)

    # ИСПОЛЬЗУЕМ ПРАВИЛЬНЫЙ МЕТОД ИЗ МОДЕЛИ
    document_status_list = client.get_document_checklist()

    return render(request, 'clients/partials/document_checklist.html', {
        'client': client,
        'document_status_list': document_status_list
    })


@login_required
def dashboard_redirect_view(request):
    """
    Перенаправляет пользователя в зависимости от его статуса.
    Сотрудников - на список клиентов, клиентов - на их профиль.
    """
    if request.user.is_staff:
        return redirect('clients:client_list')
    else:
        return redirect('portal:profile_detail')


def get_price_for_service(request, service_value):
    # Словарь с вашими ценами
    prices = {
        'study_service': 1400.00,
        'work_service': 1800.00,
        'consultation': 180.00,
        # Добавьте остальные цены по аналогии
    }
    # Находим цену по ключу. Если ключа нет, вернется 0.00
    price = prices.get(service_value, 0.00)
    return JsonResponse({'price': price})