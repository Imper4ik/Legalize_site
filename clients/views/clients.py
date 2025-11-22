from __future__ import annotations

from django.contrib import messages
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView
from django.conf import settings

from clients.constants import DOCUMENT_CHECKLIST
from clients.forms import (
    CalculatorForm,
    ClientForm,
    DocumentRequirementAddForm,
    DocumentRequirementEditForm,
    PaymentForm,
)
from clients.models import Client, Document, DocumentRequirement, Payment
from clients.services.calculator import (
    EUR_TO_PLN_RATE,
    LIVING_ALLOWANCE,
    MAX_MONTHS_LIVING,
    calculate_calculator_result,
)
from clients.services.notifications import (
    send_expired_documents_email,
    send_required_documents_email,
)
from clients.views.base import StaffRequiredMixin, staff_required_view
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
        response = super().form_valid(form)
        sent_count = send_required_documents_email(self.object)
        if sent_count:
            messages.info(self.request, "Список необходимых документов отправлен на email клиента.")
        return response

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
        previous_fingerprints_date = self.object.fingerprints_date
        messages.success(self.request, "Данные клиента успешно обновлены!")
        response = super().form_valid(form)

        new_fingerprints_date = form.cleaned_data.get("fingerprints_date")
        if new_fingerprints_date and new_fingerprints_date != previous_fingerprints_date:
            sent_count = send_expired_documents_email(self.object)
            if sent_count:
                messages.info(
                    self.request,
                    "Письмо с просроченными документами отправлено клиенту.",
                )

        return response


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
    if not request.user.is_authenticated:
        return redirect('account_login')

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

    form = CalculatorForm(request.POST or None)
    form_data = {}
    result = None
    if request.method == 'POST':
        if form.is_valid():
            result = calculate_calculator_result(form.cleaned_data)
            form_data = form.cleaned_data
        else:
            form_data = form.data
            messages.error(request, _("Ошибка. Пожалуйста, заполните все поля корректными значениями."))

    context = {
        'living_allowance': LIVING_ALLOWANCE,
        'eur_to_pln_rate': float(EUR_TO_PLN_RATE),
        'max_months_living': MAX_MONTHS_LIVING,
        'form': form,
        'form_data': form_data,
        'results': result,
    }

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


@staff_required_view
def document_checklist_manage_view(request):
    current_purpose = request.GET.get('purpose') or request.POST.get('purpose') or 'study'
    allowed = [choice[0] for choice in Client.APPLICATION_PURPOSE_CHOICES]
    if current_purpose not in allowed:
        current_purpose = allowed[0]

    if not DocumentRequirement.objects.filter(application_purpose=current_purpose).exists():
        initial_docs = DOCUMENT_CHECKLIST.get((current_purpose, 'pl'), [])
        for idx, (code, label) in enumerate(initial_docs):
            DocumentRequirement.objects.create(
                application_purpose=current_purpose,
                document_type=code,
                custom_name=label,
                position=idx,
                is_required=True,
            )

    requirements = DocumentRequirement.objects.filter(application_purpose=current_purpose).order_by('position', 'id')
    add_form = DocumentRequirementAddForm(purpose=current_purpose)

    context = {
        'current_purpose': current_purpose,
        'purpose_choices': Client.APPLICATION_PURPOSE_CHOICES,
        'requirements': requirements,
        'add_form': add_form,
    }
    return render(request, 'clients/document_checklist_manage.html', context)


@staff_required_view
@require_POST
def add_document_requirement(request):
    purpose = request.POST.get('purpose')
    form = DocumentRequirementAddForm(request.POST, purpose=purpose)
    if form.is_valid():
        form.save()
        messages.success(request, _("Новый документ успешно добавлен в чеклист."))
    else:
        messages.error(request, _("Ошибка при добавлении. Возможно, имя некорректно."))
    return redirect(f"{reverse_lazy('clients:document_checklist_manage')}?purpose={purpose}")


@staff_required_view
@require_POST
def edit_document_requirement(request, pk):
    requirement = get_object_or_404(DocumentRequirement, pk=pk)
    form = DocumentRequirementEditForm(request.POST, instance=requirement)
    if form.is_valid():
        form.save()
        messages.success(request, _("Изменения сохранены."))
    else:
        messages.error(request, _("Ошибка сохранения."))
    return redirect(f"{reverse_lazy('clients:document_checklist_manage')}?purpose={requirement.application_purpose}")


@staff_required_view
@require_POST
def delete_document_requirement(request, pk):
    requirement = get_object_or_404(DocumentRequirement, pk=pk)
    purpose = requirement.application_purpose
    requirement.delete()
    messages.success(request, _("Документ удалён из списка требований."))
    return redirect(f"{reverse_lazy('clients:document_checklist_manage')}?purpose={purpose}")


# Функции-обёртки сохраняют прежние точки входа, чтобы не переписывать URLConf
client_print_view = ClientPrintView.as_view()
client_wsc_print_view = ClientWSCPrintView.as_view()
