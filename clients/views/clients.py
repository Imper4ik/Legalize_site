from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Prefetch, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, TemplateView, UpdateView

from clients.constants import DOCUMENT_CHECKLIST
from clients.forms import (
    AppSettingsForm,
    CalculatorForm,
    ClientForm,
    DocumentChecklistForm,
    DocumentRequirementAddForm,
    DocumentRequirementEditForm,
    DocumentUploadForm,
    PaymentForm,
    ServicePriceForm,
    StaffUserCreateForm,
    StaffUserUpdateForm,
    StaffTaskForm,
)
from clients.models import AppSettings, Client, ClientActivity, Document, DocumentRequirement, Payment, ServicePrice, StaffTask, WniosekSubmission
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
from clients.services.responses import apply_no_store
from clients.services.roles import (
    ADMIN_PANEL_ALLOWED_ROLES,
    CHECKLIST_MANAGE_ROLES,
    CLIENT_DELETE_ROLES,
    CLIENT_EDIT_ROLES,
    PEOPLE_ALLOWED_ROLES,
    PREDEFINED_ROLES,
    SETTINGS_ALLOWED_ROLES,
    ensure_predefined_roles,
)
from clients.services.wniosek import record_wniosek_submission
from clients.use_cases.client_records import (
    finalize_client_creation,
    finalize_client_update,
    snapshot_client_update_state,
)
from clients.use_cases.document_requirements import delete_document_requirement_record
from clients.views.base import RoleRequiredMixin, role_required_view, StaffRequiredMixin
from clients.services.activity import log_client_view
from clients.services.access import accessible_clients_queryset
from submissions.forms import SubmissionForm
from submissions.models import Submission


class ClientListView(StaffRequiredMixin, ListView):
    model = Client
    template_name = "clients/clients_list.html"
    context_object_name = "clients"
    paginate_by = 15

    def get_queryset(self):
        queryset = accessible_clients_queryset(
            self.request.user,
            Client.objects.filter(Q(user__is_staff=False) | Q(user__isnull=True)),
        )

        company_id = self.request.GET.get("company")
        if company_id:
            queryset = queryset.filter(company_id=company_id)

        query = self.request.GET.get("q", "")
        if query:
            case_number_hash = Client.hash_case_number(query)
            return queryset.filter(
                Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
                | Q(phone__icontains=query)
                | Q(case_number_hash=case_number_hash)
            ).distinct().order_by("-created_at")
        return queryset.order_by("-created_at")

    def get_context_data(self, **kwargs):
        from clients.models import Company

        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "")
        context["selected_company"] = self.request.GET.get("company", "")
        context["companies"] = Company.objects.all()
        return context


class ClientDetailView(StaffRequiredMixin, DetailView):
    model = Client
    template_name = "clients/client_detail.html"

    def get_queryset(self):
        return accessible_clients_queryset(
            self.request.user,
            (
            Client.objects.select_related("user")
            .prefetch_related(
                Prefetch("payments", queryset=Payment.objects.order_by("-created_at")),
                Prefetch("documents", queryset=Document.objects.order_by("-uploaded_at")),
                Prefetch(
                    "staff_tasks",
                    queryset=StaffTask.objects.select_related("assignee", "created_by").order_by(
                        "status",
                        "due_date",
                        "-created_at",
                    ),
                ),
                Prefetch(
                    "activities",
                    queryset=ClientActivity.objects.select_related("actor", "document", "payment", "task").order_by(
                        "-created_at"
                    ),
                ),
                Prefetch(
                    "wniosek_submissions",
                    queryset=WniosekSubmission.objects.prefetch_related("attachments").order_by("-confirmed_at"),
                ),
                "reminders",
                "email_logs",
            )
            ),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.object
        document_status_list = client.get_document_checklist() if hasattr(client, "get_document_checklist") else []

        context["payment_form"] = PaymentForm()
        context["document_upload_form"] = DocumentUploadForm()
        context["document_status_list"] = document_status_list
        context["email_logs"] = client.email_logs.all()[:50]
        context["service_choices"] = Payment.SERVICE_CHOICES
        context["task_form"] = StaffTaskForm(initial={"assignee": self.request.user.pk})
        context["open_tasks"] = [task for task in client.staff_tasks.all() if task.status in {"open", "in_progress"}][:10]
        context["recent_activities"] = client.activities.all()[:25]
        context["workflow_summary"] = client.get_workflow_summary(document_status_list=document_status_list)
        context["workflow_alerts"] = context["workflow_summary"]["alerts"]
        return context

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        log_client_view(client=self.object, actor=request.user, request=request)
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)


class ClientCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = ["Admin", "Manager", "Staff"]
    model = Client
    form_class = ClientForm
    template_name = "clients/client_form.html"
    success_url = reverse_lazy("clients:client_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Добавить нового клиента")
        return context

    def form_valid(self, form):
        if not form.instance.assigned_staff_id:
            form.instance.assigned_staff = self.request.user
        messages.success(self.request, _("Клиент успешно добавлен!"))
        with transaction.atomic():
            self.object = form.save()
            finalize_client_creation(
                client=self.object,
                actor=self.request.user,
                send_required_email=send_required_documents_email,
            )
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        messages.error(
            self.request,
            _("Не удалось сохранить клиента. Проверьте выделенные поля и попробуйте снова."),
        )
        return super().form_invalid(form)


class ClientUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = ["Admin", "Manager", "Staff"]
    model = Client
    form_class = ClientForm
    template_name = "clients/client_form.html"

    def get_queryset(self):
        return accessible_clients_queryset(self.request.user, Client.objects.all())

    def get_success_url(self):
        return reverse_lazy("clients:client_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Редактировать данные клиента")
        return context

    def form_valid(self, form):
        previous_fingerprints_date = self.object.fingerprints_date
        previous_values = snapshot_client_update_state(self.object)
        messages.success(self.request, _("Данные клиента успешно обновлены!"))
        with transaction.atomic():
            self.object = form.save()
            finalize_client_update(
                client=self.object,
                actor=self.request.user,
                previous_values=previous_values,
                previous_fingerprints_date=previous_fingerprints_date,
                new_fingerprints_date=form.cleaned_data.get("fingerprints_date"),
                send_expired_email=send_expired_documents_email,
            )
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        messages.error(
            self.request,
            _("Не удалось сохранить клиента. Проверьте выделенные поля и попробуйте снова."),
        )
        return super().form_invalid(form)


class ClientDeleteView(RoleRequiredMixin, DeleteView):
    allowed_roles = ["Admin", "Manager", "Staff"]
    model = Client
    template_name = "clients/client_confirm_delete.html"
    success_url = reverse_lazy("clients:client_list")

    def get_queryset(self):
        return accessible_clients_queryset(self.request.user, Client.objects.all())

    def form_valid(self, form):
        client_name = self.get_object()
        messages.success(self.request, _("Клиент %(name)s был успешно удалён.") % {"name": client_name})
        return super().form_valid(form)


def dashboard_redirect_view(request):
    if not request.user.is_authenticated:
        return redirect("account_login")

    if request.user.is_staff:
        return redirect("clients:client_list")

    support_email = getattr(settings, "DEFAULT_FROM_EMAIL", "support@example.com")
    context = {
        "support_email": support_email,
        "error_title": _("Доступ запрещен"),
    }
    return render(request, "403.html", context=context, status=403)


def calculator_view(request):
    form = CalculatorForm(request.POST or None)
    form_data = {}
    result = None
    if request.method == "POST":
        if form.is_valid():
            result = calculate_calculator_result(form.cleaned_data)
            form_data = form.cleaned_data
        else:
            form_data = form.data
            messages.error(request, _("Ошибка. Пожалуйста, заполните все поля корректными значениями."))

    context = {
        "living_allowance": LIVING_ALLOWANCE,
        "eur_to_pln_rate": float(get_eur_to_pln_rate()),
        "max_months_living": MAX_MONTHS_LIVING,
        "form": form,
        "form_data": form_data,
        "results": result,
    }

    response = render(request, "clients/calculator.html", context)
    return apply_no_store(response)


class ClientPrintBaseView(StaffRequiredMixin, DetailView):
    model = Client
    context_object_name = "client"

    def get_queryset(self):
        return accessible_clients_queryset(self.request.user, Client.objects.all())


class ClientPrintView(ClientPrintBaseView):
    template_name = "clients/client_printable.html"


class ClientWSCPrintView(ClientPrintBaseView):
    template_name = "clients/client_wsc_print.html"


class ClientDocumentPrintView(ClientPrintBaseView):
    ATTACHMENT_DEFAULT_SLOTS = 5
    ATTACHMENT_MAX_SLOTS = 15
    DEFAULT_OFFICE_LINES = [
        "Mazowiecki Urząd Wojewódzki",
        "W Warszawie",
        "Ul. Marszałkowska 3/5",
        "00-624 Warszawa",
    ]
    DEFAULT_PROXY_LINES = [
        "Ajżan Bartosik-Nisanbajewa",
        "UL. MARSZAŁKOWSKA 9/15,",
        "00-626 WARSZAWA, tel. 667066113",
        "Pełnomocnik",
    ]

    documents = {
        "acceleration_request": {
            "template": "clients/documents/acceleration_request.html",
        },
        "mazowiecki_application": {
            "template": "clients/documents/mazowiecki_application.html",
        },
    }

    def get_template_names(self):
        doc_type = self.kwargs.get("doc_type")
        document = self.documents.get(doc_type)
        if not document:
            raise Http404("Документ не найден")
        return [document["template"]]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["doc_type"] = self.kwargs.get("doc_type")
        if context["doc_type"] == "mazowiecki_application":
            client = context["client"]
            application_date = client.submission_date or client.created_at.date()
            attachment_names = self._get_attachment_names(client)
            attachment_count = self.request.GET.get("attachment_count")
            if not attachment_count:
                filled_attachments = [name for name in attachment_names if name]
                attachment_count = len(filled_attachments) if filled_attachments else ""
            context.update(
                {
                    "current_date": timezone.localdate(),
                    "date_current": timezone.localdate(),
                    "application_date": application_date,
                    "full_name": f"{client.first_name} {client.last_name}",
                    "citizenship": client.citizenship or "",
                    "case_number": client.case_number or "",
                    "mos_id": getattr(client, "mos_id", "") or "",
                    "inpol_id": getattr(client, "inpol_id", "") or "",
                    "birth_date": getattr(client, "birth_date", ""),
                    "attachment_count": attachment_count,
                    "attachment_names": attachment_names,
                    "office_lines": self._get_multiline_param("office_line", self.DEFAULT_OFFICE_LINES),
                    "proxy_lines": self._get_multiline_param("proxy_line", self.DEFAULT_PROXY_LINES),
                    "confirm_url": reverse_lazy(
                        "clients:client_document_print_confirm",
                        kwargs={"pk": client.pk, "doc_type": context["doc_type"]},
                    ),
                    "auto_print": self.request.GET.get("auto_print") == "1",
                    "last_submission_id": self.request.GET.get("submission_id") or "",
                    "other_text": (client.basis_of_stay or "").strip(),
                    "check_pobyt_czasowy": client.application_purpose in {"study", "work", "family"},
                    "check_pobyt_staly": False,
                    "check_rezydent_ue": False,
                    "check_uznanie_obywatel": False,
                    "check_nadanie_obywatel": False,
                    "check_swiadczenia": False,
                    "check_potwierdzenie": False,
                    "check_inne": False,
                }
            )
        return context

    def _get_attachment_names(self, client) -> list[str]:
        attachments = [name.strip() for name in self.request.GET.getlist("attachments") if name.strip()]

        today = timezone.localdate()
        if client.decision_date and client.decision_date < today:
            days_overdue = (today - client.decision_date).days
            reminder_text = (
                f"Prośba o przyspieszenie wydania decyzji "
                f"(termin był {client.decision_date.strftime('%d.%m.%Y')}, {days_overdue} dni temu)"
            )
            if not any("przyspieszenie" in att.lower() for att in attachments):
                attachments.insert(0, reminder_text)

        minimum_slots = 1
        if len(attachments) < minimum_slots:
            attachments.extend([""] * (minimum_slots - len(attachments)))
        return attachments

    def _get_multiline_param(self, param_name: str, default_lines: list[str]) -> list[str]:
        values = self.request.GET.getlist(param_name)
        if not values:
            settings_attr = {
                "office_line": "mazowiecki_office_template",
                "proxy_line": "mazowiecki_proxy_template",
            }.get(param_name)
            if settings_attr:
                app_settings = AppSettings.objects.filter(pk=1).first()
                if app_settings is not None:
                    template_value = getattr(app_settings, settings_attr, "") or ""
                    return template_value.splitlines()
            return list(default_lines)
        return [value.strip() for value in values]


class DocumentChecklistManageView(RoleRequiredMixin, FormView):
    allowed_roles = list(CHECKLIST_MANAGE_ROLES)
    template_name = "clients/document_checklist_manage.html"
    form_class = DocumentChecklistForm

    @staticmethod
    def _default_required_codes(purpose: str) -> list[str]:
        for (purpose_code, purpose_label), docs in DOCUMENT_CHECKLIST.items():
            if purpose_code == purpose:
                return [code for code, _ in docs]
        return []

    def get_purpose(self) -> str:
        requested = self.request.GET.get("purpose") or self.request.POST.get("purpose")
        allowed = list(Submission.objects.values_list("slug", flat=True))
        if not allowed:
            allowed = [choice[0] for choice in Client.APPLICATION_PURPOSE_CHOICES]
        if requested in allowed:
            return requested
        return allowed[0] if allowed else ""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["purpose"] = self.get_purpose()
        return kwargs

    def form_valid(self, form):
        updated = form.save()
        messages.success(
            self.request,
            _("Чеклист обновлён. Выбрано документов: %(count)s") % {"count": updated},
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("clients:document_checklist_manage") + f"?purpose={self.get_purpose()}"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        purpose = self.get_purpose()
        submissions = list(Submission.objects.all())
        context["current_purpose"] = purpose
        context["purpose_choices"] = submissions
        context["add_form"] = DocumentRequirementAddForm(purpose=purpose)
        context["submission_edit_forms"] = [
            (submission, SubmissionForm(instance=submission, prefix=f"submission-{submission.id}"))
            for submission in submissions
        ]
        purpose_lookup = {submission.slug: submission.localized_name for submission in submissions}
        purpose_labels = dict(Client.APPLICATION_PURPOSE_CHOICES)
        context["current_purpose_label"] = purpose_lookup.get(
            purpose,
            purpose_labels.get(purpose, purpose),
        )
        context["submission_form"] = SubmissionForm()
        requirements = DocumentRequirement.objects.filter(application_purpose=purpose).order_by("position", "id")
        context["editable_requirements"] = [
            (
                requirement,
                DocumentRequirementEditForm(instance=requirement, prefix=f"req-{requirement.id}"),
            )
            for requirement in requirements
        ]
        context["requirement_lookup"] = {
            requirement.document_type: (requirement, edit_form)
            for requirement, edit_form in context["editable_requirements"]
        }
        return context


class AppSettingsUpdateView(RoleRequiredMixin, UpdateView):
    model = AppSettings
    form_class = AppSettingsForm
    template_name = "clients/app_settings_form.html"
    success_url = reverse_lazy("clients:app_settings")
    allowed_roles = list(SETTINGS_ALLOWED_ROLES)

    def get_object(self, queryset=None):
        return AppSettings.get_solo()

    def form_valid(self, form):
        messages.success(self.request, _("Настройки шаблона wniosek сохранены."))
        return super().form_valid(form)


class AdminPanelView(RoleRequiredMixin, TemplateView):
    template_name = "clients/admin_panel.html"
    allowed_roles = list(ADMIN_PANEL_ALLOWED_ROLES)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_submissions"] = Submission.objects.count()
        context["total_service_prices"] = ServicePrice.objects.count()
        context["active_clients"] = Client.objects.count()
        context["open_tasks"] = StaffTask.objects.filter(status__in=["open", "in_progress"]).count()
        context["pending_payments"] = Payment.objects.filter(status__in=["pending", "partial"]).count()
        context["total_price_sum"] = ServicePrice.objects.aggregate(total=Sum("price")).get("total") or 0
        return context


@role_required_view(*SETTINGS_ALLOWED_ROLES)
def service_price_manage_view(request):
    existing_by_code = {item.service_code: item for item in ServicePrice.objects.all()}
    forms = []

    if request.method == "POST":
        is_valid = True
        changed = 0
        for service_code, service_label in Payment.SERVICE_CHOICES:
            instance = existing_by_code.get(service_code)
            form = ServicePriceForm(
                request.POST,
                prefix=service_code,
                instance=instance,
                initial={"service_code": service_code, "price": getattr(instance, "price", 0)},
            )
            form.fields["service_code"].initial = service_code
            if form.is_valid():
                price_obj = form.save(commit=False)
                price_obj.service_code = service_code
                if instance is None or "price" in form.changed_data:
                    price_obj.save()
                    changed += 1
            else:
                is_valid = False
            forms.append((service_code, service_label, form))

        if is_valid:
            messages.success(
                request,
                _("Цены и услуги сохранены. Обновлено записей: %(count)s.") % {"count": changed},
            )
            return redirect("clients:service_price_manage")
        messages.error(request, _("Не удалось сохранить часть цен. Проверьте форму."))
    else:
        for service_code, service_label in Payment.SERVICE_CHOICES:
            instance = existing_by_code.get(service_code)
            form = ServicePriceForm(
                prefix=service_code,
                instance=instance,
                initial={"service_code": service_code, "price": getattr(instance, "price", 0)},
            )
            form.fields["service_code"].initial = service_code
            forms.append((service_code, service_label, form))

    return render(
        request,
        "clients/service_price_manage.html",
        {"price_forms": forms},
    )


@role_required_view(*SETTINGS_ALLOWED_ROLES)
def submission_manage_view(request):
    submissions = list(Submission.objects.all().order_by("-created_at"))
    edit_forms = [
        (submission, SubmissionForm(instance=submission, prefix=f"submission-{submission.id}"))
        for submission in submissions
    ]
    create_form = SubmissionForm(prefix="create")

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "create":
            create_form = SubmissionForm(request.POST, prefix="create")
            if create_form.is_valid():
                create_form.save()
                messages.success(request, _("Основание подачи создано."))
                return redirect("clients:submission_manage")
            messages.error(request, _("Не удалось создать основание подачи. Проверьте форму."))

        elif action == "update":
            submission_id = request.POST.get("submission_id")
            submission = get_object_or_404(Submission, pk=submission_id)
            form = SubmissionForm(request.POST, instance=submission, prefix=f"submission-{submission.id}")
            if form.is_valid():
                form.save()
                messages.success(request, _("Основание подачи обновлено."))
                return redirect("clients:submission_manage")
            messages.error(request, _("Не удалось обновить основание подачи. Проверьте форму."))
            edit_forms = [
                (item, form if item.pk == submission.pk else SubmissionForm(instance=item, prefix=f"submission-{item.id}"))
                for item in submissions
            ]

        elif action == "delete":
            submission_id = request.POST.get("submission_id")
            submission = get_object_or_404(Submission, pk=submission_id)
            submission.delete()
            messages.success(request, _("Основание подачи удалено."))
            return redirect("clients:submission_manage")

    return render(
        request,
        "clients/submission_manage.html",
        {
            "submission_rows": edit_forms,
            "create_form": create_form,
        },
    )


@role_required_view(*PEOPLE_ALLOWED_ROLES)
def staff_manage_view(request):
    user_model = get_user_model()
    staff_users = list(user_model.objects.filter(is_staff=True).order_by("email"))
    edit_forms = [
        (staff_user, StaffUserUpdateForm(instance=staff_user, prefix=f"user-{staff_user.id}"))
        for staff_user in staff_users
    ]
    create_form = StaffUserCreateForm(prefix="create", initial={"is_staff": True, "is_active": True})

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "create":
            create_form = StaffUserCreateForm(request.POST, prefix="create")
            if create_form.is_valid():
                create_form.save()
                messages.success(request, _("Сотрудник создан."))
                return redirect("clients:staff_manage")
            messages.error(request, _("Не удалось создать сотрудника. Проверьте форму."))

        elif action == "update":
            user_id = request.POST.get("user_id")
            staff_user = get_object_or_404(user_model, pk=user_id, is_staff=True)
            form = StaffUserUpdateForm(request.POST, instance=staff_user, prefix=f"user-{staff_user.id}")
            if form.is_valid():
                form.save()
                messages.success(request, _("Сотрудник обновлён."))
                return redirect("clients:staff_manage")
            messages.error(request, _("Не удалось обновить сотрудника. Проверьте форму."))
            edit_forms = [
                (item, form if item.pk == staff_user.pk else StaffUserUpdateForm(instance=item, prefix=f"user-{item.id}"))
                for item in staff_users
            ]

        elif action == "toggle_active":
            user_id = request.POST.get("user_id")
            staff_user = get_object_or_404(user_model, pk=user_id, is_staff=True)
            staff_user.is_active = not staff_user.is_active
            staff_user.save(update_fields=["is_active"])
            messages.success(request, _("Статус сотрудника обновлён."))
            return redirect("clients:staff_manage")

    return render(
        request,
        "clients/staff_manage.html",
        {
            "staff_rows": edit_forms,
            "create_form": create_form,
        },
    )


class DocumentTemplateHubView(RoleRequiredMixin, TemplateView):
    template_name = "clients/document_template_hub.html"
    allowed_roles = list(SETTINGS_ALLOWED_ROLES)


@role_required_view(*PEOPLE_ALLOWED_ROLES)
def role_manage_view(request):
    if request.method == "POST":
        ensure_predefined_roles()
        messages.success(request, _("Роли и права синхронизированы."))
        return redirect("clients:role_manage")

    ensure_predefined_roles()
    roles = []
    for role_name, description in PREDEFINED_ROLES.items():
        group = Group.objects.get(name=role_name)
        roles.append(
            {
                "name": role_name,
                "description": description,
                "members_count": group.user_set.count(),
                "permissions_count": group.permissions.count(),
                "members": list(group.user_set.order_by("email")[:8]),
            }
        )

    return render(
        request,
        "clients/role_manage.html",
        {"roles": roles},
    )


client_print_view = ClientPrintView.as_view()
client_wsc_print_view = ClientWSCPrintView.as_view()
client_document_print_view = ClientDocumentPrintView.as_view()


@role_required_view(*CHECKLIST_MANAGE_ROLES)
def client_document_print_confirm_view(request, pk, doc_type):
    if request.method != "POST":
        return redirect("clients:client_document_print", pk=pk, doc_type=doc_type)

    if doc_type != WniosekSubmission.DocumentKind.MAZOWIECKI_APPLICATION:
        raise Http404("Confirmation is only available for this document type")

    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=pk)
    submission = record_wniosek_submission(
        client=client,
        document_kind=doc_type,
        attachment_names=request.POST.getlist("attachments"),
        confirmed_by=request.user if request.user.is_authenticated else None,
        language=client.language,
    )

    confirmed_attachments = list(
        submission.attachments.order_by("position").values_list("entered_name", flat=True)
    )
    params: list[tuple[str, str]] = [("auto_print", "1"), ("submission_id", str(submission.pk))]
    for attachment_name in confirmed_attachments:
        params.append(("attachments", attachment_name))
    if confirmed_attachments:
        params.append(("attachment_count", str(len(confirmed_attachments))))
    for office_line in request.POST.getlist("office_line"):
        params.append(("office_line", office_line))
    for proxy_line in request.POST.getlist("proxy_line"):
        params.append(("proxy_line", proxy_line))

    messages.success(
        request,
        _("Wniosek confirmed. Submitted attachments were saved to the client checklist."),
    )
    redirect_url = reverse_lazy("clients:client_document_print", kwargs={"pk": client.pk, "doc_type": doc_type})
    return redirect(f"{redirect_url}?{urlencode(params)}")


@role_required_view(*CHECKLIST_MANAGE_ROLES)
def document_requirement_add(request):
    purpose = request.POST.get("purpose") or request.GET.get("purpose")
    allowed = list(Submission.objects.values_list("slug", flat=True))
    if not allowed:
        allowed = [choice[0] for choice in Client.APPLICATION_PURPOSE_CHOICES]
    if purpose not in allowed and allowed:
        purpose = allowed[0]

    form = DocumentRequirementAddForm(request.POST or None, purpose=purpose)
    if request.method == "POST":
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

    return redirect(reverse_lazy("clients:document_checklist_manage") + f"?purpose={purpose}")


@role_required_view(*CHECKLIST_MANAGE_ROLES)
def document_requirement_edit(request, pk):
    requirement = get_object_or_404(DocumentRequirement, pk=pk)
    form = DocumentRequirementEditForm(
        request.POST or None,
        instance=requirement,
        prefix=f"req-{requirement.id}",
    )

    if request.method == "POST":
        if form.is_valid():
            updated = form.save()
            status_text = _("обязательный") if updated.is_required else _("необязательный")
            messages.success(
                request,
                _("Документ обновлён: %(name)s (%(status)s).")
                % {
                    "name": updated.custom_name or updated.document_type.replace("_", " ").capitalize(),
                    "status": status_text,
                },
            )
        else:
            messages.error(
                request,
                _("Не удалось сохранить изменения. Проверьте форму."),
            )

    return redirect(reverse_lazy("clients:document_checklist_manage") + f"?purpose={requirement.application_purpose}")


@role_required_view(*CHECKLIST_MANAGE_ROLES)
def document_requirement_delete(request, pk):
    requirement = get_object_or_404(DocumentRequirement, pk=pk)

    if request.method == "POST":
        result = delete_document_requirement_record(requirement=requirement)
        messages.success(
            request,
            _("Документ удалён: %(name)s.") % {"name": result.requirement_name},
        )
        return redirect(reverse_lazy("clients:document_checklist_manage") + f"?purpose={result.purpose}")

    messages.error(request, _("Удаление доступно только через POST-запрос."))
    return redirect(reverse_lazy("clients:document_checklist_manage"))
