from __future__ import annotations

from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, UpdateView
from django.conf import settings

from clients.forms import (
    CalculatorForm,
    ClientForm,
    DocumentChecklistForm,
    DocumentRequirementAddForm,
    DocumentRequirementEditForm,
    DocumentUploadForm,
    PaymentForm,
    StaffTaskForm,
)
from clients.models import Client, ClientActivity, Document, DocumentRequirement, Payment, StaffTask, WniosekSubmission
from clients.constants import DOCUMENT_CHECKLIST
from clients.services.wniosek import record_wniosek_submission
from submissions.forms import SubmissionForm
from submissions.models import Submission
from clients.services.calculator import (
    LIVING_ALLOWANCE,
    MAX_MONTHS_LIVING,
    calculate_calculator_result,
    get_eur_to_pln_rate,
)
from clients.services.notifications import (
    send_expired_documents_email,
    send_required_documents_email,
)
from clients.services.activity import changed_field_labels, log_client_activity, log_client_view
from clients.views.base import StaffRequiredMixin, staff_required_view
from clients.services.responses import apply_no_store


class ClientListView(StaffRequiredMixin, ListView):
    model = Client
    template_name = 'clients/clients_list.html'
    context_object_name = 'clients'
    paginate_by = 15

    def get_queryset(self):
        queryset = Client.objects.filter(Q(user__is_staff=False) | Q(user__isnull=True))
        
        company_id = self.request.GET.get('company')
        if company_id:
            queryset = queryset.filter(company_id=company_id)
            
        query = self.request.GET.get('q', '')
        if query:
            case_number_hash = Client.hash_case_number(query)
            return queryset.filter(
                Q(first_name__icontains=query) | Q(last_name__icontains=query) |
                Q(email__icontains=query) | Q(phone__icontains=query) | Q(case_number_hash=case_number_hash)
            ).distinct().order_by('-created_at')
        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        from clients.models import Company
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        context['selected_company'] = self.request.GET.get('company', '')
        context['companies'] = Company.objects.all()
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
                Prefetch(
                    'staff_tasks',
                    queryset=StaffTask.objects.select_related('assignee', 'created_by').order_by(
                        'status', 'due_date', '-created_at'
                    ),
                ),
                Prefetch(
                    'activities',
                    queryset=ClientActivity.objects.select_related('actor', 'document', 'payment', 'task').order_by(
                        '-created_at'
                    ),
                ),
                Prefetch(
                    'wniosek_submissions',
                    queryset=WniosekSubmission.objects.prefetch_related('attachments').order_by('-confirmed_at'),
                ),
                'reminders',
                'email_logs',
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.object
        context['payment_form'] = PaymentForm()
        context['document_upload_form'] = DocumentUploadForm()
        document_status_list = client.get_document_checklist() if hasattr(client, 'get_document_checklist') else []
        context['document_status_list'] = document_status_list
        context['email_logs'] = client.email_logs.all()[:50]
        context['service_choices'] = Payment.SERVICE_CHOICES
        context['task_form'] = StaffTaskForm(initial={'assignee': self.request.user.pk})
        context['open_tasks'] = [task for task in client.staff_tasks.all() if task.status in {'open', 'in_progress'}][:10]
        context['recent_activities'] = client.activities.all()[:25]
        context['workflow_summary'] = client.get_workflow_summary(document_status_list=document_status_list)
        context['workflow_alerts'] = context['workflow_summary']['alerts']
        return context

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        log_client_view(client=self.object, actor=request.user, request=request)
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)


class ClientCreateView(StaffRequiredMixin, CreateView):
    model = Client
    form_class = ClientForm
    template_name = "clients/client_form.html"
    success_url = reverse_lazy("clients:client_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('Добавить нового клиента')
        return context

    def form_valid(self, form):
        messages.success(self.request, _("Клиент успешно добавлен!"))
        response = super().form_valid(form)
        send_required_documents_email(self.object)
        log_client_activity(
            client=self.object,
            actor=self.request.user,
            event_type="client_created",
            summary="Клиент создан",
            metadata={"workflow_stage": self.object.workflow_stage},
        )
        return response

    def form_invalid(self, form):
        messages.error(
            self.request,
            _("Не удалось сохранить клиента. Проверьте выделенные поля и попробуйте снова."),
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
        context['title'] = _('Редактировать данные клиента')
        return context

    def form_valid(self, form):
        previous_fingerprints_date = self.object.fingerprints_date
        tracked_fields = [
            "passport_num",
            "case_number",
            "status",
            "workflow_stage",
            "application_purpose",
            "fingerprints_date",
            "decision_date",
            "notes",
        ]
        previous_values = {field: getattr(self.object, field) for field in tracked_fields}
        messages.success(self.request, _("Данные клиента успешно обновлены!"))
        response = super().form_valid(form)

        new_fingerprints_date = form.cleaned_data.get("fingerprints_date")
        if new_fingerprints_date and new_fingerprints_date != previous_fingerprints_date:
            send_expired_documents_email(self.object)
        changed_fields = [field for field, old_value in previous_values.items() if getattr(self.object, field) != old_value]
        if changed_fields:
            log_client_activity(
                client=self.object,
                actor=self.request.user,
                event_type="client_updated",
                summary="Обновлены данные клиента",
                details=", ".join(changed_field_labels(self.object, changed_fields)),
                metadata={"changed_fields": changed_fields},
            )
        if "workflow_stage" in changed_fields:
            log_client_activity(
                client=self.object,
                actor=self.request.user,
                event_type="workflow_changed",
                summary="Этап workflow изменён",
                details=self.object.get_workflow_stage_display(),
                metadata={"workflow_stage": self.object.workflow_stage},
            )

        return response

    def form_invalid(self, form):
        messages.error(
            self.request,
            _("Не удалось сохранить клиента. Проверьте выделенные поля и попробуйте снова."),
        )
        return super().form_invalid(form)


class ClientDeleteView(StaffRequiredMixin, DeleteView):
    model = Client
    template_name = "clients/client_confirm_delete.html"
    success_url = reverse_lazy("clients:client_list")

    def form_valid(self, form):
        client_name = self.get_object()
        messages.success(self.request, _("Клиент %(name)s был успешно удалён.") % {"name": client_name})
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
        'eur_to_pln_rate': float(get_eur_to_pln_rate()),
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


class ClientDocumentPrintView(ClientPrintBaseView):
    """Печать отдельных документов для клиента."""

    ATTACHMENT_DEFAULT_SLOTS = 5
    ATTACHMENT_MAX_SLOTS = 15

    documents = {
        'acceleration_request': {
            'template': 'clients/documents/acceleration_request.html',
        },
        'mazowiecki_application': {
            'template': 'clients/documents/mazowiecki_application.html',
        },
    }

    def get_template_names(self):
        doc_type = self.kwargs.get('doc_type')
        document = self.documents.get(doc_type)
        if not document:
            raise Http404("Документ не найден")
        return [document['template']]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['doc_type'] = self.kwargs.get('doc_type')
        if context['doc_type'] == 'mazowiecki_application':
            client = context['client']
            application_date = client.submission_date or client.created_at.date()
            attachment_names = self._get_attachment_names(client)
            attachment_count = self.request.GET.get('attachment_count')
            if not attachment_count:
                filled_attachments = [name for name in attachment_names if name]
                attachment_count = len(filled_attachments) if filled_attachments else ''
            context.update(
                {
                    'current_date': timezone.localdate(),
                    'date_current': timezone.localdate(),
                    'application_date': application_date,
                    'full_name': f"{client.first_name} {client.last_name}",
                    'citizenship': client.citizenship or '',
                    'case_number': client.case_number or '',
                    'mos_id': getattr(client, 'mos_id', '') or '',
                    'inpol_id': getattr(client, 'inpol_id', '') or '',
                    'birth_date': getattr(client, 'birth_date', ''),
                    'attachment_count': attachment_count,
                    'attachment_names': attachment_names,
                    'confirm_url': reverse_lazy(
                        'clients:client_document_print_confirm',
                        kwargs={'pk': client.pk, 'doc_type': context['doc_type']},
                    ),
                    'auto_print': self.request.GET.get('auto_print') == '1',
                    'last_submission_id': self.request.GET.get('submission_id') or '',
                    'other_text': (client.basis_of_stay or '').strip(),
                    'check_pobyt_czasowy': client.application_purpose in {'study', 'work', 'family'},
                    'check_pobyt_staly': False,
                    'check_rezydent_ue': False,
                    'check_uznanie_obywatel': False,
                    'check_nadanie_obywatel': False,
                    'check_swiadczenia': False,
                    'check_potwierdzenie': False,
                    'check_inne': False,
                }
            )
        return context

    def _get_attachment_names(self, client) -> list[str]:
        attachments = [name.strip() for name in self.request.GET.getlist('attachments') if name.strip()]

        today = timezone.localdate()
        if client.decision_date and client.decision_date < today:
            days_overdue = (today - client.decision_date).days
            reminder_text = f"Prośba o przyspieszenie wydania decyzji (termin był {client.decision_date.strftime('%d.%m.%Y')}, {days_overdue} dni temu)"
            if not any("przyspieszenie" in att.lower() for att in attachments):
                attachments.insert(0, reminder_text)

        minimum_slots = 1
        if len(attachments) < minimum_slots:
            attachments.extend([''] * (minimum_slots - len(attachments)))
        return attachments


class DocumentChecklistManageView(StaffRequiredMixin, FormView):
    template_name = 'clients/document_checklist_manage.html'
    form_class = DocumentChecklistForm

    @staticmethod
    def _default_required_codes(purpose: str) -> list[str]:
        for (purpose_code, _), docs in DOCUMENT_CHECKLIST.items():
            if purpose_code == purpose:
                return [code for code, _ in docs]
        return []

    def get_purpose(self) -> str:
        requested = self.request.GET.get('purpose') or self.request.POST.get('purpose')
        allowed = list(Submission.objects.values_list('slug', flat=True))
        if not allowed:
            allowed = [choice[0] for choice in Client.APPLICATION_PURPOSE_CHOICES]
        if requested in allowed:
            return requested
        return allowed[0] if allowed else ''

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['purpose'] = self.get_purpose()
        return kwargs

    def form_valid(self, form):
        updated = form.save()
        messages.success(
            self.request,
            _("Чеклист обновлён. Выбрано документов: %(count)s") % {"count": updated},
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('clients:document_checklist_manage') + f'?purpose={self.get_purpose()}'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        purpose = self.get_purpose()  # вызывается один раз
        context['current_purpose'] = purpose
        context['purpose_choices'] = list(Submission.objects.all())
        context['add_form'] = DocumentRequirementAddForm(purpose=purpose)
        context['submission_edit_forms'] = [
            (submission, SubmissionForm(instance=submission, prefix=f"submission-{submission.id}"))
            for submission in context['purpose_choices']
        ]
        purpose_lookup = {submission.slug: submission.localized_name for submission in context['purpose_choices']}
        purpose_labels = dict(Client.APPLICATION_PURPOSE_CHOICES)
        context['current_purpose_label'] = purpose_lookup.get(
            purpose,
            purpose_labels.get(purpose, purpose),
        )
        context['submission_form'] = SubmissionForm()
        requirements = DocumentRequirement.objects.filter(
            application_purpose=purpose
        ).order_by('position', 'id')
        context['editable_requirements'] = [
            (
                requirement,
                DocumentRequirementEditForm(instance=requirement, prefix=f"req-{requirement.id}"),
            )
            for requirement in requirements
        ]
        context['requirement_lookup'] = {
            requirement.document_type: (requirement, edit_form)
            for requirement, edit_form in context['editable_requirements']
        }
        return context


# Функции-обёртки сохраняют прежние точки входа, чтобы не переписывать URLConf
client_print_view = ClientPrintView.as_view()
client_wsc_print_view = ClientWSCPrintView.as_view()
client_document_print_view = ClientDocumentPrintView.as_view()


@staff_required_view
def client_document_print_confirm_view(request, pk, doc_type):
    if request.method != 'POST':
        return redirect('clients:client_document_print', pk=pk, doc_type=doc_type)

    if doc_type != WniosekSubmission.DocumentKind.MAZOWIECKI_APPLICATION:
        raise Http404("Confirmation is only available for this document type")

    client = get_object_or_404(Client, pk=pk)
    submission = record_wniosek_submission(
        client=client,
        document_kind=doc_type,
        attachment_names=request.POST.getlist('attachments'),
        confirmed_by=request.user if request.user.is_authenticated else None,
        language=client.language,
    )

    confirmed_attachments = list(
        submission.attachments.order_by('position').values_list('entered_name', flat=True)
    )
    params: list[tuple[str, str]] = [('auto_print', '1'), ('submission_id', str(submission.pk))]
    for attachment_name in confirmed_attachments:
        params.append(('attachments', attachment_name))
    if confirmed_attachments:
        params.append(('attachment_count', str(len(confirmed_attachments))))

    messages.success(
        request,
        _("Wniosek confirmed. Submitted attachments were saved to the client checklist."),
    )
    redirect_url = reverse_lazy('clients:client_document_print', kwargs={'pk': client.pk, 'doc_type': doc_type})
    return redirect(f"{redirect_url}?{urlencode(params)}")


@staff_required_view
def document_requirement_add(request):
    purpose = request.POST.get('purpose') or request.GET.get('purpose')
    allowed = list(Submission.objects.values_list('slug', flat=True))
    if not allowed:
        allowed = [choice[0] for choice in Client.APPLICATION_PURPOSE_CHOICES]
    if purpose not in allowed and allowed:
        purpose = allowed[0]

    form = DocumentRequirementAddForm(request.POST or None, purpose=purpose)
    if request.method == 'POST':
        if form.is_valid():
            requirement = form.save()
            messages.success(
                request,
                _("Документ '%(name)s' добавлен в чеклист.")
                % {"name": requirement.custom_name or requirement.document_type},
            )
        else:
            messages.error(
                request,
                _("Не удалось добавить документ. Проверьте форму."),
            )

    return redirect(reverse_lazy('clients:document_checklist_manage') + f'?purpose={purpose}')


@staff_required_view
def document_requirement_edit(request, pk):
    requirement = get_object_or_404(DocumentRequirement, pk=pk)
    form = DocumentRequirementEditForm(
        request.POST or None, instance=requirement, prefix=f"req-{requirement.id}"
    )

    if request.method == 'POST':
        if form.is_valid():
            updated = form.save()
            status_text = _("обязательный") if updated.is_required else _("необязательный")
            messages.success(
                request,
                _("Документ обновлён: %(name)s (%(status)s).")
                % {
                    "name": updated.custom_name or updated.document_type.replace('_', ' ').capitalize(),
                    "status": status_text,
                },
            )
        else:
            messages.error(
                request,
                _("Не удалось сохранить изменения. Проверьте форму."),
            )

    return redirect(reverse_lazy('clients:document_checklist_manage') + f'?purpose={requirement.application_purpose}')


@staff_required_view
def document_requirement_delete(request, pk):
    requirement = get_object_or_404(DocumentRequirement, pk=pk)

    if request.method == 'POST':
        purpose = requirement.application_purpose
        name = requirement.custom_name or requirement.document_type.replace('_', ' ').capitalize()
        requirement.delete()
        messages.success(
            request,
            _("Документ удалён: %(name)s.") % {"name": name},
        )
        return redirect(reverse_lazy('clients:document_checklist_manage') + f'?purpose={purpose}')

    messages.error(request, _("Удаление доступно только через POST-запрос."))
    return redirect(reverse_lazy('clients:document_checklist_manage'))
