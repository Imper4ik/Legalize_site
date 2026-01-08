from __future__ import annotations

from collections import OrderedDict

from django.contrib import messages
from django.core.management import call_command
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views.generic import ListView

from clients.models import Client, Reminder
from clients.services.notifications import send_expiring_documents_email, send_missing_documents_email
from clients.views.base import StaffRequiredMixin, staff_required_view


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
        reminders = list(context['reminders'])
        grouped = OrderedDict()
        for reminder in reminders:
            client = reminder.client
            group = grouped.setdefault(
                client.id,
                {
                    'client': client,
                    'reminders': [],
                    'documents': [],
                    'missing_documents': [],
                },
            )
            group['reminders'].append(reminder)
            if reminder.document and reminder.document.expiry_date:
                group['documents'].append(reminder.document)

        for group in grouped.values():
            checklist = group['client'].get_document_checklist() or []
            group['missing_documents'] = [
                {
                    'name': item.get('name'),
                    'expiry_date': getattr((item.get('documents') or [None])[0], 'expiry_date', None),
                }
                for item in checklist
                if not item.get('is_uploaded')
            ]

        context.update(
            {
                'grouped_reminders': list(grouped.values()),
                'reminders_count': len(grouped),
                'total_reminders_count': len(reminders),
            }
        )
        return context


class PaymentReminderListView(ReminderListView):
    reminder_type = 'payment'
    template_name = 'clients/payment_reminder_list.html'
    title = _('Напоминания по оплатам')


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
    messages.warning(request, "Эту операцию можно выполнить только через специальную кнопку.")
    return redirect('clients:document_reminder_list')


@staff_required_view
def reminder_action(request, reminder_id):
    reminder = get_object_or_404(Reminder, pk=reminder_id)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'delete':
            reminder.delete()
            messages.success(request, _("Напоминание удалено."))
        elif action == 'deactivate':
            reminder.is_active = False
            reminder.save()
            messages.success(request, _("Напоминание отмечено как выполненное."))
        elif action == 'send_email' and reminder.reminder_type == 'document':
            documents = []
            if reminder.document and reminder.document.expiry_date:
                documents.append(reminder.document)
            sent = send_expiring_documents_email(reminder.client, documents)
            if sent:
                messages.success(request, _("Отправили письмо клиенту об истекающем документе."))
            else:
                messages.warning(request, _("Не удалось отправить письмо: нет email или даты истечения."))
    return redirect('clients:document_reminder_list')


@staff_required_view
def send_document_reminder_email(request, client_id):
    if request.method == 'POST':
        client = get_object_or_404(Client, pk=client_id)
        reminders = (
            Reminder.objects.filter(client=client, reminder_type='document', is_active=True)
            .select_related('document')
        )
        documents = [reminder.document for reminder in reminders if reminder.document and reminder.document.expiry_date]
        sent = send_expiring_documents_email(client, documents)
        if sent:
            messages.success(request, _("Отправили письмо клиенту по документам."))
        else:
            messages.warning(request, _("Не удалось отправить письмо: нет email или документов с датой истечения."))
        return redirect('clients:document_reminder_list')
    messages.warning(request, _("Эту операцию можно выполнить только через кнопку отправки."))
    return redirect('clients:document_reminder_list')
