from __future__ import annotations

import copy
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from clients.security.sanitizer import sanitize_user_html
from clients.services.access import accessible_clients_queryset
from clients.services.calculator import CURRENCY_EUR, CURRENCY_PLN
from clients.services.roles import user_has_any_role
from clients.services.workflow import validate_client_workflow_transition
from clients.use_cases.document_requirements import (
    build_document_requirement_code,
    create_document_requirement_for_purpose,
    sync_document_checklist_for_purpose,
    update_document_requirement_record,
)
from clients.validators import FILE_INPUT_ACCEPT, validate_uploaded_document
from submissions.models import Submission

from .constants import INTERNAL_DOCS, DocumentType
from .models import (
    AppSettings,
    Case,
    Client,
    Company,
    Document,
    DocumentRequirement,
    EmailLog,
    EmployeePermission,
    FamilyGroup,
    Payment,
    ServicePrice,
    StaffTask,
    get_fallback_document_checklist,
    resolve_document_label,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

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


class AppSettingsForm(forms.ModelForm):
    class Meta:
        model = AppSettings
        fields = [
            "organization_name",
            "contact_email",
            "contact_phone",
            "office_address",
            "default_proxy_name",
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
        cleaned = super().clean()
        password1 = cleaned.get("password1") if cleaned else None
        password2 = cleaned.get("password2") if cleaned else None
        if cleaned and password1 != password2:
            self.add_error("password2", "Passwords do not match.")
        if password1 and password1 == password2:
            user = self.instance or self.Meta.model(
                email=cleaned.get("email"),
                first_name=cleaned.get("first_name", ""),
                last_name=cleaned.get("last_name", ""),
            )
            validate_password(password1, user=user)
        return cleaned or {}

    def save(self, commit: bool = True) -> Any:
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            self.save_m2m()
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

def _label_for_document_type(code: str) -> str:
    try:
        return str(DocumentType(code).label)
    except ValueError:
        return code.replace('_', ' ').capitalize()



class CaseForm(forms.ModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = Case
        fields = [
            "application_purpose",
            "application_type",
            "basis_of_stay",
            "workflow_stage",
            "assigned_staff",
            "company",
            "version",
        ]
        widgets = {
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
        self.fields["assigned_staff"].queryset = user_model.objects.filter(
            is_staff=True,
            is_active=True,
        ).order_by("email")
        self.fields["assigned_staff"].required = False
        self.fields["company"].required = False


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
    submission_date = forms.DateField(
        label=_("Дата подачи (Złożone)"),
        required=False,
        input_formats=['%d.%m.%Y', '%d-%m-%Y', '%Y-%m-%d'],
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('дд.мм.гггг')})
    )
    fingerprints_date = forms.DateField(
        label=_("Дата сдачи отпечатков"),
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
            for field_name in ("assigned_staff", "status", "workflow_stage"):
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
            'birth_date', 'passport_num', 'case_number', 'application_purpose', 'language',
            'company', 'assigned_staff', 'status', 'workflow_stage',
            'basis_of_stay', 'legal_basis_end_date', 'submission_date',
            'employer_phone',
            'fingerprints_date', 'family_role', 'sponsor_client', 'notes'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'citizenship': forms.TextInput(attrs={'class': 'form-control'}),
            'birth_date': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('дд.мм.гггг')}),
            'passport_num': forms.TextInput(attrs={'class': 'form-control'}),
            'case_number': forms.TextInput(attrs={'class': 'form-control'}),
            'language': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'workflow_stage': forms.Select(attrs={'class': 'form-select'}),
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

        next_stage = cleaned_data.get("workflow_stage")
        previous_stage = getattr(self.instance, "workflow_stage", None)

        temp_client = copy.copy(self.instance)
        for field_name, value in cleaned_data.items():
            if hasattr(temp_client, field_name):
                setattr(temp_client, field_name, value)

        transition_result = validate_client_workflow_transition(
            client=temp_client,
            previous_stage=previous_stage,
            next_stage=next_stage,
        )
        if not transition_result.allowed:
            self.add_error("workflow_stage", transition_result.message)

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


class MassEmailForm(forms.Form):
    subject = forms.CharField(
        label=_("Тема письма"),
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _("Например: Важное обновление")})
    )
    message = forms.CharField(
        label=_("Текст письма"),
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 6})
    )
    company = forms.ModelChoiceField(
        queryset=Company.objects.all(),
        label=_("Фильтр по Компании"),
        required=False,
        empty_label=_("Все компании"),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    status = forms.ChoiceField(
        label=_("Фильтр по Статусу"),
        required=False,
        choices=[('', _("Все статусы"))] + list(Client.STATUS_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class DocumentUploadForm(forms.ModelForm):
    def __init__(self, *args: Any, doc_type: str | None = None, client: Client | None = None, case: Case | None = None, **kwargs: Any) -> None:
        self.doc_type = doc_type
        self.client = client
        self.case = case
        super().__init__(*args, **kwargs)
        # Assign owners onto the instance so model-level clean() can resolve the
        # required Case (an explicit case, or the single-case legacy fallback)
        # during form validation, before the document is saved.
        if client is not None:
            self.instance.client = client
        if case is not None:
            self.instance.case = case
        if doc_type is not None:
            self.instance.document_type = doc_type
        self.fields["zus_period_month"].help_text = _(
            "Для ZUS RCA укажите месяц отчёта. Если загружаете страховой полис, добавьте его как отдельный документ «Polisa ubezpieczeniowa / Health insurance»."
        )

    def clean_file(self) -> Any:
        return validate_uploaded_document(self.cleaned_data.get("file"))

    def clean_zus_period_month(self) -> Any:
        value = self.cleaned_data.get("zus_period_month")
        if self.doc_type != DocumentType.ZUS_RCA_OR_INSURANCE.value:
            return None
        if not value:
            return None
        normalized = value.replace(day=1)
        if self.client is not None:
            duplicate_query = Document.objects.filter(
                client=self.client,
                document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
                zus_period_month=normalized,
                archived_at__isnull=True,
            )
            case = self.case
            if case is not None:
                duplicate_query = duplicate_query.filter(case=case)
            if duplicate_query.exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError(_("ZUS RCA for this month is already uploaded for this case."))
        return normalized

    class Meta:
        model = Document
        fields = ['file', 'expiry_date', 'zus_period_month']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control', 'accept': FILE_INPUT_ACCEPT}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'zus_period_month': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }


class PaymentForm(forms.ModelForm):
    payment_date = forms.DateField(
        required=False,
        input_formats=['%d.%m.%Y', '%d-%m-%Y', '%Y-%m-%d'],
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    due_date = forms.DateField(
        required=False,
        input_formats=['%d.%m.%Y', '%d-%m-%Y', '%Y-%m-%d'],
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    amount_paid = forms.DecimalField(
        required=False,
        initial=0,
        min_value=Decimal("0.00"),
        localize=True,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'})
    )
    total_amount = forms.DecimalField(
        min_value=Decimal("0.00"),
        localize=True,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'})
    )
    status = forms.ChoiceField(
        required=False,
        choices=Payment.PAYMENT_STATUS_CHOICES,
        initial='pending',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Payment
        fields = [
            "service_description",
            "total_amount",
            "amount_paid",
            "status",
            "payment_method",
            "payment_date",
            "due_date",
            "transaction_id",
        ]
        widgets = {
            "service_description": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "payment_method": forms.Select(attrs={"class": "form-select"}),
            "total_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "amount_paid": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "transaction_id": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean_amount_paid(self) -> Decimal:
        return cast(Decimal, self.cleaned_data.get("amount_paid") or Decimal("0.00"))


class ClientDocumentRequirementForm(forms.ModelForm):
    class Meta:
        from clients.models import ClientDocumentRequirement
        model = ClientDocumentRequirement
        fields = ["name", "description", "is_required", "due_date"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_required": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def clean_name(self) -> str:
        return str(self.cleaned_data["name"]).strip()


class FamilyGroupFinanceForm(forms.ModelForm):
    class Meta:
        model = FamilyGroup
        fields = [
            "sponsor_monthly_income",
            "monthly_support_per_person",
            "monthly_housing_cost",
            "meldunek_free_housing",
        ]
        widgets = {
            "sponsor_monthly_income": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0"}
            ),
            "monthly_support_per_person": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0"}
            ),
            "monthly_housing_cost": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0"}
            ),
            "meldunek_free_housing": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class StaffTaskForm(forms.ModelForm):
    due_date = forms.DateField(
        required=False,
        input_formats=['%d.%m.%Y', '%d-%m-%Y', '%Y-%m-%d'],
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )

    class Meta:
        model = StaffTask
        fields = ['title', 'description', 'priority', 'status', 'assignee', 'due_date']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'assignee': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        user_model = get_user_model()
        staff_qs = user_model.objects.filter(is_staff=True, is_active=True).order_by('email')
        if hasattr(self.fields['assignee'], 'queryset'):
            setattr(self.fields['assignee'], 'queryset', staff_qs)
        self.fields['assignee'].required = False


class DocumentRequirementEditForm(forms.ModelForm):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not self.instance.custom_name:
            self.initial.setdefault('custom_name', _label_for_document_type(self.instance.document_type))
        self.fields['position'].required = False

    class Meta:
        model = DocumentRequirement
        fields = ['custom_name', 'custom_name_pl', 'custom_name_en', 'custom_name_ru', 'position', 'is_required']
        widgets = {
            'custom_name': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'custom_name_pl': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'custom_name_en': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'custom_name_ru': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'position': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
            'is_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def save(self, commit: bool = True) -> DocumentRequirement:
        instance = self.instance
        result = update_document_requirement_record(
            requirement=instance,
            cleaned_data=self.cleaned_data,
        )
        if result.requirement is None:
            raise RuntimeError("Document requirement update did not return a record")
        return result.requirement


class DocumentRequirementAddForm(forms.Form):
    name = forms.CharField(
        label=_('Название документа'),
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    def __init__(self, *args: Any, purpose: str | None = None, **kwargs: Any) -> None:
        self.purpose = purpose
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs.setdefault('autofocus', 'autofocus')

    def clean_name(self) -> str:
        name = (self.cleaned_data.get('name') or '').strip()
        self.cleaned_data['slug'] = build_document_requirement_code(
            purpose=self.purpose or "",
            name=name,
        )
        return name

    def save(self) -> DocumentRequirement:
        if not hasattr(self, 'cleaned_data'):
            raise RuntimeError("Call is_valid() before save()")
        result = create_document_requirement_for_purpose(
            purpose=self.purpose or "",
            name=self.cleaned_data['name'],
            slug=self.cleaned_data['slug'],
        )
        if result.requirement is None:
            raise RuntimeError("Document requirement creation did not return a record")
        return result.requirement


class DocumentChecklistForm(forms.Form):
    required_documents = forms.MultipleChoiceField(
        label=_('Необходимые документы'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        choices=DocumentType.choices,
    )

    def __init__(self, *args: Any, purpose: str | None = None, **kwargs: Any) -> None:
        self.purpose = purpose
        super().__init__(*args, **kwargs)
        existing_requirements = list(
            DocumentRequirement.objects.filter(application_purpose=self.purpose)
            .order_by('position', 'id')
        )

        choices: list[tuple[str, str]] = []

        if existing_requirements:
            for requirement in existing_requirements:
                if requirement.document_type in INTERNAL_DOCS:
                    continue
                label = resolve_document_label(
                    requirement.document_type,
                    requirement.custom_name,
                    requirement.custom_name_pl,
                    requirement.custom_name_en,
                    requirement.custom_name_ru,
                    translation.get_language(),
                )
                choices.append((requirement.document_type, label))
        else:
            fallback_docs = get_fallback_document_checklist(self.purpose or "")
            if fallback_docs:
                choices.extend([(str(doc[0]), str(doc[1])) for doc in fallback_docs if doc[0] not in INTERNAL_DOCS])
            else:
                choices.extend([(str(c[0]), str(c[1])) for c in DocumentType.choices if c[0] not in INTERNAL_DOCS])

        cast(forms.MultipleChoiceField, self.fields['required_documents']).choices = choices

        if 'required_documents' not in self.initial:
            self.initial['required_documents'] = self._initial_documents()

    @staticmethod
    def _label_for_code(code: str) -> str:
        return _label_for_document_type(code)

    def _initial_documents(self) -> list[str]:
        existing = (
            DocumentRequirement.objects.filter(application_purpose=self.purpose, is_required=True)
            .exclude(document_type__in=INTERNAL_DOCS)
            .order_by('position', 'id')
            .values_list('document_type', flat=True)
        )
        if existing:
            return list(existing)

        if DocumentRequirement.objects.filter(application_purpose=self.purpose).exists():
            return []

        fallback_docs = get_fallback_document_checklist(self.purpose or "")
        if fallback_docs:
            return [str(code) for code, _ in fallback_docs if code not in INTERNAL_DOCS]
        return []

    def save(self, *, doc_order: list[str] | None = None) -> int:
        selected_codes = list(self.cleaned_data.get('required_documents', []))
        if doc_order:
            # Re-order selected codes according to the D&D ordering.
            ordered = [code for code in doc_order if code in selected_codes]
            remaining = [code for code in selected_codes if code not in ordered]
            selected_codes = ordered + remaining
        result = sync_document_checklist_for_purpose(
            purpose=self.purpose or "",
            selected_codes=selected_codes,
        )
        return result.updated_count


class CalculatorForm(forms.Form):
    total_end_date = forms.DateField(
        input_formats=['%d-%m-%Y'],
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('дд-мм-гггг')}),
    )
    tuition_fee = forms.DecimalField(min_value=0, decimal_places=2, max_digits=10)
    tuition_currency = forms.ChoiceField(choices=((CURRENCY_PLN, 'PLN'), (CURRENCY_EUR, 'EUR')))
    fee_type = forms.ChoiceField(
        choices=(('per_month', 'per_month'), ('per_semester', 'per_semester'), ('per_year', 'per_year')),
        required=False,
    )
    months_in_period = forms.IntegerField(min_value=1)
    rent_and_bills = forms.DecimalField(min_value=0, decimal_places=2, max_digits=10)
    rent_currency = forms.ChoiceField(choices=((CURRENCY_PLN, 'PLN'), (CURRENCY_EUR, 'EUR')))
    num_people = forms.IntegerField(min_value=1)
    has_border = forms.BooleanField(required=False)
    basis_of_stay = forms.ChoiceField(
        choices=(('student', _('Студент')), ('family_reunification', _('Воссоединение семьи'))),
        initial='student',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


# --- LOG FILTER FORMS ---


class EmailLogFilterForm(forms.Form):
    status = forms.ChoiceField(
        choices=[("", _("Все статусы"))] + EmailLog.DELIVERY_STATUS_CHOICES,
        required=False,
        label=_("Статус"),
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    date_start = forms.DateField(
        required=False,
        label=_("С даты"),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
    date_end = forms.DateField(
        required=False,
        label=_("По дату"),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
    search = forms.CharField(
        required=False,
        label=_("Поиск"),
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-sm",
                "placeholder": _("Тема или имя клиента..."),
            }
        ),
    )


class StaffActivityFilterForm(forms.Form):
    actor = forms.ModelChoiceField(
        queryset=User.objects.filter(is_staff=True).order_by("email"),
        required=False,
        empty_label=_("Все сотрудники"),
        label=_("Сотрудник"),
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    date_start = forms.DateField(
        required=False,
        label=_("С даты"),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
    date_end = forms.DateField(
        required=False,
        label=_("По дату"),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
