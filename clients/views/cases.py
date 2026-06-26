from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, HttpResponseBase
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views.generic import CreateView, DetailView, UpdateView

from clients.forms import CaseForm
from clients.models import Case, CaseArchiveBatch, ClientActivity, Document, Payment, Reminder, StaffTask
from clients.services.access import accessible_cases_queryset, accessible_clients_queryset
from clients.services.archive import archive_case as archive_case_service
from clients.services.archive import restore_case as restore_case_service
from clients.services.cases import create_case_for_client
from clients.services.locking import update_case_with_version
from clients.services.roles import CLIENT_MUTATION_ROLES, RESTORE_ALLOWED_ROLES
from clients.views.base import RoleRequiredMixin, role_required_view


class CaseDetailView(RoleRequiredMixin, DetailView):
    allowed_roles = list(CLIENT_MUTATION_ROLES)
    model = Case
    template_name = "clients/case_detail.html"
    context_object_name = "case"

    def get_queryset(self) -> Any:
        return accessible_cases_queryset(
            self.request.user,
            Case.all_objects.select_related("client", "company")
            .prefetch_related("documents", "payments", "reminders", "staff_tasks", "activities"),
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        case = self.object
        context["documents"] = Document.all_objects.filter(case=case).order_by("-uploaded_at")[:200]
        # Checklist grouped by required document (the pre-refactor view): one row
        # per requirement with status, missing items flagged, files nested inside.
        context["document_status_list"] = case.client.get_document_checklist(
            check_file_existence=True, case=case
        )
        context["payments"] = Payment.all_objects.filter(case=case).order_by("-created_at")[:50]
        context["tasks"] = StaffTask.objects.filter(case=case).select_related("assignee").order_by("status", "due_date")[:50]
        context["reminders"] = Reminder.objects.filter(case=case).order_by("-is_active", "due_date")[:50]
        context["activities"] = ClientActivity.objects.filter(case=case).select_related("actor").order_by("-created_at")[:50]
        context["next_action"] = _case_next_action(case)
        from clients.forms import PaymentForm, StaffTaskForm
        context["payment_form"] = PaymentForm()
        context["task_form"] = StaffTaskForm(initial={"assignee": self.request.user.pk})
        return context


class CaseCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = list(CLIENT_MUTATION_ROLES)
    model = Case
    form_class = CaseForm
    template_name = "clients/case_form.html"

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        self.client_obj = get_object_or_404(
            accessible_clients_queryset(request.user),
            pk=kwargs["pk"],
        )
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        initial.update({
            "application_purpose": self.client_obj.application_purpose,
            "basis_of_stay": self.client_obj.basis_of_stay or "",
            # New cases start at the initial stage; process state lives on the
            # Case now, not the Client (spec §4).
            "workflow_stage": "new_client",
            "company": self.client_obj.company_id,
        })
        return initial

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["client"] = self.client_obj
        return context

    def form_valid(self, form: CaseForm) -> HttpResponse:
        case = create_case_for_client(
            client=self.client_obj,
            actor=self.request.user,
            authority_case_number=(form.cleaned_data.get("authority_case_number") or "").strip(),
            application_purpose=form.cleaned_data.get("application_purpose") or "",
            application_type=form.cleaned_data.get("application_type") or "",
            basis_of_stay=form.cleaned_data.get("basis_of_stay") or "",
            workflow_stage=form.cleaned_data.get("workflow_stage") or "new_client",
            submission_date=form.cleaned_data.get("submission_date"),
            fingerprints_date=form.cleaned_data.get("fingerprints_date"),
            company=form.cleaned_data.get("company"),
        )
        messages.success(self.request, _("Case created."))
        return redirect(case.get_absolute_url())


class CaseUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = list(CLIENT_MUTATION_ROLES)
    model = Case
    form_class = CaseForm
    template_name = "clients/case_form.html"

    def get_queryset(self) -> Any:
        return accessible_cases_queryset(
            self.request.user,
            Case.all_objects.select_related("client", "company"),
        )

    def form_valid(self, form: CaseForm) -> HttpResponse:
        case = self.object
        expected_version = form.cleaned_data.get("version")
        if expected_version is None:
            expected_version = case.version

        authority_case_number = (form.cleaned_data.get("authority_case_number") or "").strip()
        changes_dict: dict[str, Any] = {
            "authority_case_number": authority_case_number,
            "application_purpose": form.cleaned_data.get("application_purpose") or "",
            "application_type": form.cleaned_data.get("application_type") or "",
            "basis_of_stay": form.cleaned_data.get("basis_of_stay") or "",
            "workflow_stage": form.cleaned_data.get("workflow_stage") or case.workflow_stage,
            "submission_date": form.cleaned_data.get("submission_date"),
            "fingerprints_date": form.cleaned_data.get("fingerprints_date"),
            "company": form.cleaned_data.get("company"),
        }
        # Once a real authority number is entered by hand, the migrated legacy
        # number and its manual-check flag are no longer needed (spec 3.10).
        if authority_case_number:
            changes_dict["legacy_case_number"] = ""
            changes_dict["needs_manual_number_check"] = False

        try:
            update_case_with_version(
                case_id=case.id,
                expected_version=expected_version,
                actor=self.request.user,
                changes_dict=changes_dict,
            )
            messages.success(self.request, _("Case updated."))
        except ValidationError as e:
            form.add_error(None, e)
            return self.form_invalid(form)
        return redirect(case.get_absolute_url())


@role_required_view(*CLIENT_MUTATION_ROLES)
def archive_case_view(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        return redirect("clients:client_list")
    case = get_object_or_404(accessible_cases_queryset(request.user, Case.objects.select_related("client")), pk=pk)
    archive_case_service(case=case, actor=request.user)
    messages.success(request, _("Case archived."))
    return redirect("clients:client_detail", pk=case.client_id)


@role_required_view(*RESTORE_ALLOWED_ROLES)
def restore_case_view(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        return redirect("clients:client_list")
    case = get_object_or_404(accessible_cases_queryset(request.user, Case.all_objects.select_related("client")), pk=pk)
    batch = CaseArchiveBatch.objects.filter(case=case, status="archived").first()
    if not batch:
        messages.error(request, _("No active archive batch found for this case."))
        return redirect("clients:case_detail", pk=case.pk)
    restore_case_service(case=case, actor=request.user, batch=batch)
    messages.success(request, _("Case restored."))
    return redirect("clients:case_detail", pk=case.pk)


def _case_next_action(case: Case) -> str:
    return {
        "new_client": _("Collect basic case data."),
        "document_collection": _("Collect and verify required documents."),
        "application_submitted": _("Track authority confirmation and prepare fingerprints."),
        "fingerprints": _("Confirm fingerprints appointment."),
        "waiting_decision": _("Monitor decision deadline."),
        "decision_received": _("Review decision and close follow-up tasks."),
        "closed": _("No active action."),
    }.get(case.workflow_stage, _("Review case status."))
