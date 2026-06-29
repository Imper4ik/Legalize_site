from __future__ import annotations

from typing import Any

from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from clients.services.onboarding_purposes import ONBOARDING_PURPOSE_CHOICES


class ClientIntakeSubmissionForm(forms.Form):
    first_name = forms.CharField(label=_("First name"), max_length=100)
    last_name = forms.CharField(label=_("Last name"), max_length=100)
    email = forms.EmailField(label=_("Email"))
    phone = forms.CharField(label=_("Phone"), max_length=32)
    birth_date = forms.DateField(
        label=_("Date of birth"),
        input_formats=["%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"],
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    citizenship = forms.CharField(label=_("Citizenship"), max_length=100)
    passport_number = forms.CharField(label=_("Passport number"), max_length=100)
    language = forms.ChoiceField(label=_("Communication language"), choices=settings.LANGUAGES)
    application_purpose = forms.ChoiceField(label=_("Application purpose"), choices=ONBOARDING_PURPOSE_CHOICES)
    application_type = forms.CharField(label=_("Application type"), max_length=64, required=False)
    basis_of_stay = forms.CharField(label=_("Basis of stay"), max_length=100, required=False)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {css_class}".strip()
        self.fields["application_type"].widget.attrs["placeholder"] = "temporary residence"
        self.fields["basis_of_stay"].widget.attrs["placeholder"] = "work, study, family"

    def personal_payload(self) -> dict[str, Any]:
        return {
            "first_name": self.cleaned_data["first_name"].strip(),
            "last_name": self.cleaned_data["last_name"].strip(),
            "email": self.cleaned_data["email"].strip().lower(),
            "phone": self.cleaned_data["phone"].strip(),
            "birth_date": self.cleaned_data["birth_date"].isoformat(),
            "citizenship": self.cleaned_data["citizenship"].strip(),
            "document_number": self.cleaned_data["passport_number"].strip(),
            "language": self.cleaned_data["language"],
        }

    def case_payload(self) -> dict[str, Any]:
        return {
            "application_purpose": self.cleaned_data["application_purpose"],
            "application_type": self.cleaned_data["application_type"].strip(),
            "basis_of_stay": self.cleaned_data["basis_of_stay"].strip(),
            "workflow_stage": "new_client",
            "status": "new",
        }
