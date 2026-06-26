from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib import messages
from django.db.models import Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import TemplateView, UpdateView

from clients.constants import ACTIVE_WORKFLOW_STAGES
from clients.forms import (
    AppSettingsForm,
    ServicePriceForm,
)
from clients.models import AppSettings, Case, Client, Document, Payment, Reminder, ServicePrice, StaffTask
from clients.services.roles import (
    ADMIN_PANEL_ALLOWED_ROLES,
    CRITICAL_SETTINGS_ALLOWED_ROLES,
    SETTINGS_ALLOWED_ROLES,
)
from clients.views.base import RoleRequiredMixin, role_required_view
from submissions.forms import SubmissionForm
from submissions.models import Submission


class AdminPanelView(RoleRequiredMixin, TemplateView):
    template_name = "clients/admin_panel.html"
    allowed_roles = list(ADMIN_PANEL_ALLOWED_ROLES)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        upcoming_cutoff = today + timedelta(days=30)
        context["total_submissions"] = Submission.objects.count()
        context["total_service_prices"] = ServicePrice.objects.count()
        context["active_clients"] = Client.objects.count()
        # Count active Cases (not Clients): Case.objects already excludes archived
        # cases, and we drop the finished workflow stages (spec section 10).
        context["active_cases"] = Case.objects.exclude(
            workflow_stage__in=["closed", "decision_received"]
        ).count()
        context["ocr_awaiting_review"] = Document.objects.filter(awaiting_confirmation=True, client__archived_at__isnull=True).count()
        from django.db.models import Q
        context["documents_awaiting_verification"] = Document.objects.filter(
            file__gt="",
            verified=False,
            awaiting_confirmation=False,
            archived_at__isnull=True,
            client__archived_at__isnull=True,
        ).exclude(
            Q(rejection_reason__isnull=False) & ~Q(rejection_reason="")
        ).exclude(
            expiry_date__isnull=False,
            expiry_date__lt=today,
        ).count()
        context["missing_documents"] = _count_missing_document_items()
        context["expired_documents"] = Document.objects.filter(
            expiry_date__isnull=False,
            expiry_date__lt=today,
            client__archived_at__isnull=True,
        ).count()
        context["open_tasks"] = StaffTask.objects.filter(status__in=["open", "in_progress"], client__archived_at__isnull=True).count()
        context["pending_payments"] = Payment.objects.filter(status__in=["pending", "partial"], client__archived_at__isnull=True).count()
        # Process state lives on the case: count cases, not clients (spec §4/§10).
        context["upcoming_fingerprints"] = Case.objects.filter(
            fingerprints_date__isnull=False,
            fingerprints_date__gte=today,
            fingerprints_date__lte=upcoming_cutoff,
        ).count()
        context["waiting_after_fingerprints"] = Case.objects.filter(
            workflow_stage="waiting_decision",
            fingerprints_date__isnull=False,
            fingerprints_date__lte=today,
            decision_date__isnull=True,
        ).count()
        context["decisions_received"] = Case.objects.filter(decision_date__isnull=False).count()
        context["active_reminders"] = Reminder.objects.filter(is_active=True, client__archived_at__isnull=True).count()
        context["total_price_sum"] = ServicePrice.objects.aggregate(total=Sum("price")).get("total") or 0
        context["test_center_available"] = bool(
            getattr(self.request.user, "is_superuser", False)
        )
        context["demo_center_available"] = bool(
            getattr(self.request.user, "is_superuser", False)
        )
        return context


def _count_missing_document_items() -> int | str:
    # Active = the client has at least one active (non-finished) case (spec §4).
    active_qs = Client.objects.filter(
        cases__workflow_stage__in=ACTIVE_WORKFLOW_STAGES
    ).distinct()

    # Для огромных баз данных мы не можем считать это в реальном времени,
    # так как это требует создания чеклистов для каждого клиента.
    if active_qs.count() > 500:
        return "500+ (Расчет отключен для скорости)"

    clients = active_qs.prefetch_related(
        "documents",
        "custom_document_requirements",
        "wniosek_submissions__confirmed_by",
        "wniosek_submissions__attachments",
    )
    requirements_cache: dict[str, Any] = {}
    return sum(
        1
        for client in clients
        for item in client.get_document_checklist(requirements_cache=requirements_cache)
        if not item.get("is_complete")
    )


class AppSettingsUpdateView(RoleRequiredMixin, UpdateView):
    model = AppSettings
    form_class = AppSettingsForm
    template_name = "clients/app_settings_form.html"
    success_url = reverse_lazy("clients:app_settings")
    allowed_roles = list(CRITICAL_SETTINGS_ALLOWED_ROLES)

    def get_object(self, queryset: Any = None) -> AppSettings:
        return AppSettings.get_solo()

    def form_valid(self, form: AppSettingsForm) -> HttpResponse:
        messages.success(self.request, _("Настройки шаблона wniosek сохранены."))
        return super().form_valid(form)


class DocumentTemplateHubView(RoleRequiredMixin, TemplateView):
    template_name = "clients/document_template_hub.html"
    allowed_roles = list(SETTINGS_ALLOWED_ROLES)


@role_required_view(*SETTINGS_ALLOWED_ROLES)
def service_price_manage_view(request: HttpRequest) -> HttpResponse:
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
def submission_manage_view(request: HttpRequest) -> HttpResponse:
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
