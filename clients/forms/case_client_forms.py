from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING, Any, cast

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from clients.models import (
    Case,
    Client,
)
from clients.security.sanitizer import sanitize_user_html
from clients.services.access import accessible_clients_queryset
from clients.services.roles import user_has_any_role
from clients.services.workflow import validate_case_workflow_transition
from submissions.models import Submission

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

logger = logging.getLogger(__name__)
User = get_user_model()


class CaseForm(forms.ModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput(), required=False)
    # Process dates live on the case (spec §4); accept the same dd.mm.yyyy input
    # the client form used to offer.
    submission_date = forms.DateField(
        label=_("Дата подачи (Złożone)"),
        required=False,
        input_formats=["%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d"],
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": _("дд.мм.гггг")}),
    )
    fingerprints_date = forms.DateField(
        label=_("Дата сдачи отпечатков"),
        required=False,
        input_formats=["%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d"],
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": _("дд.мм.гггг")}),
    )

    class Meta:
        model = Case
        fields = [
            "authority_case_number",
            "application_purpose",
            "application_type",
            "basis_of_stay",
            "workflow_stage",
            "submission_date",
            "fingerprints_date",
            "assigned_staff",
            "company",
            "version",
        ]
        widgets = {
            "authority_case_number": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "WSC-II-P.6151.138285.2025"}
            ),
            "application_purpose": forms.TextInput(attrs={"class": "form-control"}),
            "application_type": forms.TextInput(attrs={"class": "form-control"}),
            "basis_of_stay": forms.TextInput(attrs={"class": "form-control"}),
            "workflow_stage": forms.Select(attrs={"class": "form-select"}),
            "assigned_staff": forms.Select(attrs={"class": "form-select"}),
            "company": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        user_model = get_user_model()
        cast(forms.ModelChoiceField, self.fields["assigned_staff"]).queryset = user_model.objects.filter(
            is_staff=True,
            is_active=True,
        ).order_by("email")
        self.fields["assigned_staff"].required = False
        self.fields["company"].required = False

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        if cleaned_data is None:
            return {}

        # The case is the process carrier, so workflow transitions are validated
        # here (spec §4). Overlay the cleaned values onto a copy of the instance
        # so date-dependent rules (submission/fingerprints/decision, open
        # payments) are checked against the about-to-be-saved state.
        next_stage = cleaned_data.get("workflow_stage")
        previous_stage = getattr(self.instance, "workflow_stage", None)
        temp_case = copy.copy(self.instance)
        for field_name, value in cleaned_data.items():
            if hasattr(temp_case, field_name):
                setattr(temp_case, field_name, value)

        transition_result = validate_case_workflow_transition(
            case=temp_case,
            previous_stage=previous_stage,
            next_stage=next_stage,
        )
        if not transition_result.allowed:
            self.add_error("workflow_stage", transition_result.message)

        return cleaned_data


class ClientForm(forms.ModelForm):
    application_purpose = forms.ChoiceField(
        label=_("Цель подачи"),
        choices=[],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    # --- FIXED HERE ---
    # We explicitly define the date fields to make them not required
    # and to specify the correct date format from the calendar.
    legal_basis_end_date = forms.DateField(
        label=_("Дата окончания основания"),
        required=False,
        input_formats=['%d.%m.%Y', '%d-%m-%Y', '%Y-%m-%d'],
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('дд.мм.гггг')})
    )
    birth_date = forms.DateField(
        label=_("Дата рождения"),
        required=False,
        input_formats=['%d.%m.%Y', '%d-%m-%Y', '%Y-%m-%d'],
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('дд.мм.гггг')})
    )
    def __init__(self, *args: Any, user: AbstractBaseUser | AnonymousUser | None = None, **kwargs: Any) -> None:
        self.user = user
        super().__init__(*args, **kwargs)

        # Use localized_name so application purpose is translated
        reserved_purposes = Client.FAMILY_MEMBER_REQUIREMENT_PURPOSES
        submissions = [
            (sub.slug, str(sub.localized_name))
            for sub in Submission.objects.exclude(slug__in=reserved_purposes)
        ]
        choices: list[tuple[str, str]] = []
        if submissions:
            choices = submissions
        else:
            choices = [(str(value), str(label)) for value, label in Client.APPLICATION_PURPOSE_CHOICES]

        existing_choice_values = {value for value, _label in choices}
        for value, label in Client.APPLICATION_PURPOSE_CHOICES:
            if value not in existing_choice_values:
                choices.append((str(value), str(label)))
                existing_choice_values.add(value)

        current_value = (
            self.data.get(self.add_prefix('application_purpose'))
            or self.initial.get('application_purpose')
            or getattr(self.instance, 'application_purpose', None)
        )
        if (
            current_value
            and current_value not in reserved_purposes
            and current_value not in {value for value, _label in choices}
        ):
            choices.append((str(current_value), str(current_value)))

        cast(forms.ChoiceField, self.fields['application_purpose']).choices = choices

        # Fixed typing for queryset assignment
        staff_qs = get_user_model().objects.filter(
            is_staff=True,
            is_active=True,
        ).order_by('email')
        if hasattr(self.fields['assigned_staff'], 'queryset'):
            setattr(self.fields['assigned_staff'], 'queryset', staff_qs)

        sponsor_queryset = Client.objects.exclude(pk=self.instance.pk)
        if self.user is not None:
            sponsor_queryset = cast(Any, accessible_clients_queryset(self.user, sponsor_queryset))
        else:
            sponsor_queryset = Client.objects.none()

        if hasattr(self.fields['sponsor_client'], 'queryset'):
            setattr(self.fields['sponsor_client'], 'queryset', sponsor_queryset.order_by('last_name', 'first_name'))

        if self._is_limited_staff_user():
            for field_name in ("assigned_staff", "status"):
                self.fields.pop(field_name, None)

    def _is_limited_staff_user(self) -> bool:
        user = self.user
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        return user_has_any_role(user, "Staff") and not user_has_any_role(user, "Admin", "Manager")

    class Meta:
        model = Client
        fields = [
            'first_name', 'last_name', 'email', 'phone', 'citizenship',
            'birth_date', 'passport_num', 'application_purpose', 'language',
            'company', 'assigned_staff', 'status',
            'basis_of_stay', 'legal_basis_end_date',
            'employer_phone',
            'family_role', 'sponsor_client', 'notes'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'citizenship': forms.TextInput(attrs={'class': 'form-control'}),
            'birth_date': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('дд.мм.гггг')}),
            'passport_num': forms.TextInput(attrs={'class': 'form-control'}),
            'language': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'company': forms.Select(attrs={'class': 'form-select'}),
            'assigned_staff': forms.Select(attrs={'class': 'form-select'}),
            'family_role': forms.Select(attrs={'class': 'form-select'}),
            'sponsor_client': forms.Select(attrs={'class': 'form-select'}),
            'basis_of_stay': forms.TextInput(attrs={'class': 'form-control'}),
            'employer_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_notes(self) -> str | None:
        notes = self.cleaned_data.get('notes')
        if not notes:
            return notes
        return sanitize_user_html(notes)

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        if cleaned_data is None:
            return {}
        application_purpose = cleaned_data.get("application_purpose")
        family_role = cleaned_data.get("family_role") or ""
        sponsor_client = cleaned_data.get("sponsor_client")

        family_member_roles = Client.FAMILY_MEMBER_REQUIREMENT_PURPOSES

        if application_purpose == "family":
            if not family_role:
                self.add_error("family_role", _("Select a family role."))
            elif family_role == "sponsor":
                cleaned_data["sponsor_client"] = None
            elif family_role in family_member_roles:
                if sponsor_client is None:
                    self.add_error("sponsor_client", _("Select a sponsor."))
                else:
                    self._validate_sponsor_relationship(sponsor_client)
            else:
                self.add_error("family_role", _("Family members must be spouse or child."))
        else:
            cleaned_data["sponsor_client"] = None
            has_family_members = bool(
                self.instance.pk
                and self.instance.sponsored_family_members.exists()
            )
            if not has_family_members or family_role != "sponsor":
                cleaned_data["family_role"] = ""

        # Workflow stage is no longer edited on the client: it lives on the case
        # and is validated by CaseForm (spec §4).
        return cleaned_data

    def _validate_sponsor_relationship(self, sponsor_client: Client) -> None:
        if self.instance.pk and sponsor_client.pk == self.instance.pk:
            self.add_error("sponsor_client", _("A client cannot sponsor themselves."))
            return

        if not self.instance.pk:
            return

        seen: set[int] = set()
        current: Client | None = sponsor_client
        while current is not None and current.pk:
            if current.pk == self.instance.pk:
                self.add_error("sponsor_client", _("Sponsor relationship cannot create a cycle."))
                return
            if current.pk in seen:
                return
            seen.add(current.pk)
            current = current.sponsor_client
