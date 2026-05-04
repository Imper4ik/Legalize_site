from __future__ import annotations

from types import SimpleNamespace

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import FormView

from clients.constants import DOCUMENT_CHECKLIST
from clients.forms import (
    DocumentChecklistForm,
    DocumentRequirementAddForm,
    DocumentRequirementEditForm,
)
from clients.models import Client, DocumentRequirement
from clients.services.roles import CHECKLIST_MANAGE_ROLES
from clients.use_cases.document_requirements import delete_document_requirement_record
from clients.views.base import RoleOrFeatureRequiredMixin, role_or_feature_required_view
from submissions.forms import SubmissionForm
from submissions.models import Submission


FAMILY_CHECKLIST_PURPOSES = (
    SimpleNamespace(
        slug="family_spouse",
        localized_name=_("Воссоединение — супруг/супруга"),
        is_system=True,
    ),
    SimpleNamespace(
        slug="family_child",
        localized_name=_("Воссоединение — ребёнок"),
        is_system=True,
    ),
)


def _system_family_purpose_slugs() -> list[str]:
    return [purpose.slug for purpose in FAMILY_CHECKLIST_PURPOSES]


def _allowed_checklist_purposes() -> list[str]:
    allowed = list(Submission.objects.values_list("slug", flat=True))
    if not allowed:
        allowed = [choice[0] for choice in Client.APPLICATION_PURPOSE_CHOICES]
    for slug in _system_family_purpose_slugs():
        if slug not in allowed:
            allowed.append(slug)
    return allowed


class DocumentChecklistManageView(RoleOrFeatureRequiredMixin, FormView):
    allowed_roles = list(CHECKLIST_MANAGE_ROLES)
    required_permission_name = "can_manage_checklists"
    template_name = "clients/document_checklist_manage.html"
    form_class = DocumentChecklistForm

    @staticmethod
    def _default_required_codes(purpose: str) -> list[str]:
        for (purpose_code, _language_code), docs in DOCUMENT_CHECKLIST.items():
            if purpose_code == purpose:
                return [code for code, _ in docs]
        return []

    def get_purpose(self) -> str:
        requested = self.request.GET.get("purpose") or self.request.POST.get("purpose")
        allowed = _allowed_checklist_purposes()
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
        purpose_choices = [*submissions, *FAMILY_CHECKLIST_PURPOSES]
        context["current_purpose"] = purpose
        context["purpose_choices"] = purpose_choices
        context["add_form"] = DocumentRequirementAddForm(purpose=purpose)
        context["submission_edit_forms"] = [
            (submission, SubmissionForm(instance=submission, prefix=f"submission-{submission.id}"))
            for submission in submissions
        ]
        purpose_lookup = {submission.slug: submission.localized_name for submission in submissions}
        purpose_lookup.update({purpose.slug: purpose.localized_name for purpose in FAMILY_CHECKLIST_PURPOSES})
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


@role_or_feature_required_view("can_manage_checklists", *CHECKLIST_MANAGE_ROLES)
def document_requirement_add(request):
    purpose = request.POST.get("purpose") or request.GET.get("purpose")
    allowed = _allowed_checklist_purposes()
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


@role_or_feature_required_view("can_manage_checklists", *CHECKLIST_MANAGE_ROLES)
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


@role_or_feature_required_view("can_manage_checklists", *CHECKLIST_MANAGE_ROLES)
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
