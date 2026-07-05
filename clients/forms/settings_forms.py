from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _

from clients.models import (
    AppSettings,
    EmployeePermission,
    ServicePrice,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
User = get_user_model()


EMPLOYEE_PERMISSION_FIELD_LABELS = (
    ("can_manage_payments", _("Управление платежами")),
    ("can_send_custom_email", _("Отправка custom email")),
    ("can_send_mass_email", _("Массовые рассылки")),
    ("can_export_clients", _("Экспорт клиентов")),
    ("can_delete_clients", _("Удаление клиентов")),
    ("can_delete_documents", _("Удаление документов")),
    ("can_manage_checklists", _("Управление чеклистами")),
    ("can_view_reports", _("Просмотр отчётов")),
    ("can_manage_staff_tasks", _("Управление задачами")),
    ("can_run_ocr_review", _("Доступ к OCR review")),
)


def _build_permission_fields() -> dict[str, forms.BooleanField]:
    return {
        name: forms.BooleanField(required=False, label=label)
        for name, label in EMPLOYEE_PERMISSION_FIELD_LABELS
    }


def _sync_verified_email_address(user: Any) -> None:
    """Keep the allauth EmailAddress verified for admin-managed staff accounts.

    ACCOUNT_EMAIL_VERIFICATION is mandatory, so a staff user created here
    without a verified EmailAddress would be locked on the "confirm your
    email" page until a verification email arrives. The admin created the
    account in person, so the address is treated as verified.
    """
    from allauth.account.models import EmailAddress

    email_address, _created = EmailAddress.objects.get_or_create(
        user=user,
        email__iexact=user.email,
        defaults={"email": user.email, "primary": True, "verified": True},
    )
    if not email_address.verified or not email_address.primary or email_address.email != user.email:
        email_address.email = user.email
        email_address.verified = True
        email_address.primary = True
        email_address.save(update_fields=["email", "verified", "primary"])
    EmailAddress.objects.filter(user=user).exclude(pk=email_address.pk).update(primary=False)


class AppSettingsForm(forms.ModelForm):
    class Meta:
        model = AppSettings
        fields = [
            "organization_name",
            "contact_email",
            "contact_phone",
            "office_address",
            "default_proxy_name",
            "legal_entity_name",
            "data_controller_nip",
            "data_controller_regon",
            "data_controller_krs",
            "legal_address",
            "representative_name",
            "dpo_contact",
            "privacy_policy_version",
            "data_retention_summary",
            "privacy_policy_body",
            "mazowiecki_office_template",
            "mazowiecki_proxy_template",
        ]
        widgets = {
            "organization_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("Legalize / Expowiza / название вашей организации")}
            ),
            "contact_email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "office@example.com"}
            ),
            "contact_phone": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "+48 000 000 000"}
            ),
            "office_address": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "UL. PRZYKLADOWA 1/2\n00-000 WARSZAWA",
                }
            ),
            "default_proxy_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Imie Nazwisko"}
            ),
            "legal_entity_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("ООО / Sp. z o.o. — полное наименование")}
            ),
            "data_controller_nip": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "0000000000"}
            ),
            "data_controller_regon": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "000000000"}
            ),
            "data_controller_krs": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "0000000000"}
            ),
            "legal_address": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "UL. PRZYKLADOWA 1/2\n00-000 WARSZAWA",
                }
            ),
            "representative_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("Imie Nazwisko, должность")}
            ),
            "dpo_contact": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "iod@example.com"}
            ),
            "privacy_policy_version": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "2026-01"}
            ),
            "data_retention_summary": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("5 лет после закрытия дела")}
            ),
            "privacy_policy_body": forms.Textarea(
                attrs={"class": "form-control", "rows": 6}
            ),
            "mazowiecki_office_template": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 6,
                    "placeholder": "Mazowiecki Urzad Wojewodzki\nW Warszawie\nUl. Marszalkowska 3/5\n00-624 Warszawa",
                }
            ),
            "mazowiecki_proxy_template": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 6,
                    "placeholder": "Imie Nazwisko\nUL. ADRES 1/2,\n00-000 MIASTO, tel. 000000000\nPelnomocnik",
                }
            ),
        }


class ServicePriceForm(forms.ModelForm):
    class Meta:
        model = ServicePrice
        fields = ["service_code", "price"]
        widgets = {
            "service_code": forms.Select(attrs={"class": "form-select"}),
            "price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
        }


class StaffUserCreateForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )
    password2 = forms.CharField(
        label="Repeat password",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all().order_by("name"),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
    )

    class Meta:
        model = get_user_model()
        fields = ["email", "first_name", "last_name", "is_staff", "is_active", "groups"]
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "is_staff": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 != password2:
            self.add_error("password2", "Passwords do not match.")
        if password1 and password1 == password2:
            user = self.instance or self.Meta.model(
                email=cleaned.get("email") or "",
                first_name=cleaned.get("first_name", ""),
                last_name=cleaned.get("last_name", ""),
            )
            validate_password(password1, user=user)
        return cleaned

    def save(self, commit: bool = True) -> Any:
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            self.save_m2m()
            _sync_verified_email_address(user)
        return user


class StaffUserUpdateForm(forms.ModelForm):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all().order_by("name"),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
    )

    class Meta:
        model = get_user_model()
        fields = ["email", "first_name", "last_name", "is_staff", "is_active", "groups"]
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "is_staff": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field_name, field in _build_permission_fields().items():
            field.widget.attrs.setdefault("class", "form-check-input")
            self.fields[field_name] = field

        permission_object = getattr(self.instance, "employee_permission", None)
        for field_name, _label in EMPLOYEE_PERMISSION_FIELD_LABELS:
            self.fields[field_name].initial = bool(
                getattr(permission_object, field_name, False) if permission_object else False
            )

    def save(self, commit: bool = True) -> Any:
        user = super().save(commit=commit)
        if commit:
            _sync_verified_email_address(user)
        permission_object, _ = EmployeePermission.objects.get_or_create(user=user)
        updated_fields: list[str] = []
        for field_name, _label in EMPLOYEE_PERMISSION_FIELD_LABELS:
            value = bool(self.cleaned_data.get(field_name, False))
            if getattr(permission_object, field_name) != value:
                setattr(permission_object, field_name, value)
                updated_fields.append(field_name)
        if updated_fields:
            permission_object.save(update_fields=[*updated_fields, "updated_at"])
            logger.warning(
                "Role permissions updated for user_id=%s. Updated fields: %s",
                user.id,
                updated_fields,
            )
        return user
