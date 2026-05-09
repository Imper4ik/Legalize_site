from __future__ import annotations

from types import SimpleNamespace
from typing import Any, TYPE_CHECKING

from django.contrib import messages
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
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

if TYPE_CHECKING:
    pass


FAMILY_CHECKLIST_PURPOSES = (
    SimpleNamespace(
        slug="family_spouse",
        localized_name=str(_("Воссоединение — супруг/супруга")),
        is_system=True,
    ),
    SimpleNamespace(
        slug="family_child",
        localized_name=str(_("Воссоединение — ребёнок")),
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

    @staticmethod
    def _system_purpose_choices(existing_slugs: set[str] | None = None) -> list[SimpleNamespace]:
        existing_slugs = existing_slugs or set()
        return [
            SimpleNamespace(slug=value, localized_name=label, id="", is_system=True)
            for value, label in Client.DOCUMENT_REQUIREMENT_PURPOSE_CHOICES
            if value not in existing_slugs
        ]

    @staticmethod
    def _submission_queryset() -> QuerySet[Submission]:
        return Submission.objects.exclude(slug__in=Client.FAMILY_MEMBER_REQUIREMENT_PURPOSES)

    def _allowed_purposes(self) -> list[str]:
        submission_slugs = list(self._submission_queryset().values_list("slug", flat=True))
        system_slugs = [value for value, _label in Client.DOCUMENT_REQUIREMENT_PURPOSE_CHOICES]
        return list(dict.fromkeys([*submission_slugs, *system_slugs]))

    def get_purpose(self) -> str:
        requested = self.request.GET.get("purpose") or self.request.POST.get("purpose")
        allowed = self._allowed_purposes()
        if requested in allowed:
            return str(requested)
        return allowed[0] if allowed else ""

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["purpose"] = self.get_purpose()
        return kwargs

    def form_valid(self, form: DocumentChecklistForm) -> HttpResponse:
        updated = form.save()
        messages.success(
            self.request,
            _("Чеклист обновлён. Выбрано документов: %(count)s") % {"count": updated},
        )
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return str(reverse_lazy("clients:document_checklist_manage") + f"?purpose={self.get_purpose()}")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        purpose = self.get_purpose()
        submissions = list(self._submission_queryset())
        submission_slugs = {submission.slug for submission in submissions}
        system_choices = self._system_purpose_choices(submission_slugs)
        context["current_purpose"] = purpose
        context["purpose_choices"] = [*submissions, *system_choices]
        context["add_form"] = DocumentRequirementAddForm(purpose=purpose)
        context["submission_edit_forms"] = [
            (submission, SubmissionForm(instance=submission, prefix=f"submission-{submission.id}"))
            for submission in submissions
        ]
        purpose_lookup = {submission.slug: submission.localized_name for submission in submissions}
        purpose_labels = dict(Client.DOCUMENT_REQUIREMENT_PURPOSE_CHOICES)
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
def document_requirement_add(request: HttpRequest) -> HttpResponse:
    purpose = request.POST.get("purpose") or request.GET.get("purpose")
    reserved = Client.FAMILY_MEMBER_REQUIREMENT_PURPOSES
    allowed = list(Submission.objects.exclude(slug__in=reserved).values_list("slug", flat=True))
    allowed = list(dict.fromkeys([*allowed, *[choice[0] for choice in Client.DOCUMENT_REQUIREMENT_PURPOSE_CHOICES]]))
    if purpose not in allowed and allowed:
        purpose = allowed[0]

    form = DocumentRequirementAddForm(request.POST or None, purpose=str(purpose))
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

    return redirect(str(reverse_lazy("clients:document_checklist_manage") + f"?purpose={purpose}"))


@role_or_feature_required_view("can_manage_checklists", *CHECKLIST_MANAGE_ROLES)
def document_requirement_edit(request: HttpRequest, pk: int) -> HttpResponse:
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

    return redirect(str(reverse_lazy("clients:document_checklist_manage") + f"?purpose={requirement.application_purpose}"))


@role_or_feature_required_view("can_manage_checklists", *CHECKLIST_MANAGE_ROLES)
def document_requirement_delete(request: HttpRequest, pk: int) -> HttpResponse:
    requirement = get_object_or_404(DocumentRequirement, pk=pk)

    if request.method == "POST":
        result = delete_document_requirement_record(requirement=requirement)
        messages.success(
            request,
            _("Документ удалён: %(name)s.") % {"name": result.requirement_name},
        )
        return redirect(str(reverse_lazy("clients:document_checklist_manage") + f"?purpose={result.purpose}"))

    messages.error(request, _("Удаление доступно только через POST-запрос."))
    return redirect(str(reverse_lazy("clients:document_checklist_manage")))
