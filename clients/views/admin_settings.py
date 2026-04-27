from __future__ import annotations

from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import TemplateView, UpdateView

from clients.forms import (
    AppSettingsForm,
    ServicePriceForm,
)
from clients.models import AppSettings, Client, Payment, ServicePrice, StaffTask
from clients.services.roles import (
    ADMIN_PANEL_ALLOWED_ROLES,
    SETTINGS_ALLOWED_ROLES,
)
from clients.views.base import RoleRequiredMixin, role_required_view
from submissions.forms import SubmissionForm
from submissions.models import Submission


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


class DocumentTemplateHubView(RoleRequiredMixin, TemplateView):
    template_name = "clients/document_template_hub.html"
    allowed_roles = list(SETTINGS_ALLOWED_ROLES)


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
