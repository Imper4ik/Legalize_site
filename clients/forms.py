from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from clients.services.calculator import CURRENCY_EUR, CURRENCY_PLN
from clients.services.workflow import validate_client_workflow_transition
from clients.use_cases.document_requirements import (
    build_document_requirement_code,
    create_document_requirement_for_purpose,
    sync_document_checklist_for_purpose,
    update_document_requirement_record,
)
from clients.validators import FILE_INPUT_ACCEPT, validate_uploaded_document
from .constants import DocumentType, INTERNAL_DOCS
from submissions.models import Submission
from .models import (
    AppSettings,
    Client,
    Company,
    Document,
    DocumentRequirement,
    Payment,
    ServicePrice,
    StaffTask,
    EmployeePermission,
    get_fallback_document_checklist,
    resolve_document_label,
)


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


def _build_permission_fields():
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
                attrs={"class": "form-control", "placeholder": "Legalize / Expowiza / название вашей организации"}
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

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            self.add_error("password2", "Passwords do not match.")
        return cleaned

    def clean_is_superuser(self):
        return False

    def save(self, commit=True):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in _build_permission_fields().items():
            field.widget.attrs.setdefault("class", "form-check-input")
            self.fields[field_name] = field

        permission_object = getattr(self.instance, "employee_permission", None)
        for field_name, _label in EMPLOYEE_PERMISSION_FIELD_LABELS:
            self.fields[field_name].initial = bool(
                getattr(permission_object, field_name, False) if permission_object else False
            )

    def save(self, commit=True):
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
            # TODO: Wire employee permission updates into a dedicated global audit log
            # once the project has a non-client-scoped audit model.
        return user

def _label_for_document_type(code: str) -> str:
    try:
        return DocumentType(code).label
    except ValueError:
        return code.replace('_', ' ').capitalize()


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Use localized_name so application purpose is translated
        submissions = [(sub.slug, sub.localized_name) for sub in Submission.objects.all()]
        if submissions:
            choices = submissions
        else:
            choices = list(Client.APPLICATION_PURPOSE_CHOICES)

        current_value = (
            self.data.get(self.add_prefix('application_purpose'))
            or self.initial.get('application_purpose')
            or getattr(self.instance, 'application_purpose', None)
        )
        if current_value and current_value not in {value for value, _label in choices}:
            choices.append((current_value, current_value))

        self.fields['application_purpose'].choices = choices
        self.fields['assigned_staff'].queryset = get_user_model().objects.filter(
            is_staff=True,
            is_active=True,
        ).order_by('email')

    class Meta:
        model = Client
        fields = [
            'first_name', 'last_name', 'email', 'phone', 'citizenship',
            'birth_date', 'passport_num', 'case_number', 'application_purpose', 'language',
            'company', 'assigned_staff', 'status', 'workflow_stage',
            'basis_of_stay', 'legal_basis_end_date', 'submission_date',
            'employer_phone',
            'fingerprints_date', 'notes'
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
            'basis_of_stay': forms.TextInput(attrs={'class': 'form-control'}),
            'employer_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        next_stage = cleaned_data.get("workflow_stage")
        previous_stage = getattr(self.instance, "workflow_stage", None)

        temp_client = self.instance
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
        choices=[('', _("Все статусы"))] + Client.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class DocumentUploadForm(forms.ModelForm):
    def clean_file(self):
        return validate_uploaded_document(self.cleaned_data.get("file"))

    class Meta:
        model = Document
        fields = ['file', 'expiry_date']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control', 'accept': FILE_INPUT_ACCEPT}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
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
        localize=True,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    total_amount = forms.DecimalField(
        localize=True,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
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
            'service_description', 'total_amount', 'amount_paid', 'status',
            'payment_method', 'payment_date', 'due_date', 'transaction_id'
        ]
        widgets = {
            'service_description': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'total_amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'amount_paid': forms.NumberInput(attrs={'class': 'form-control'}),
            'transaction_id': forms.TextInput(attrs={'class': 'form-control'}),
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user_model = get_user_model()
        self.fields['assignee'].queryset = user_model.objects.filter(is_staff=True, is_active=True).order_by('email')
        self.fields['assignee'].required = False


class DocumentRequirementEditForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.custom_name:
            self.initial.setdefault('custom_name', _label_for_document_type(self.instance.document_type))

    class Meta:
        model = DocumentRequirement
        fields = ['custom_name', 'custom_name_pl', 'custom_name_en', 'custom_name_ru', 'is_required']
        widgets = {
            'custom_name': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'custom_name_pl': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'custom_name_en': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'custom_name_ru': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'is_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def save(self, commit=True):
        instance = self.instance
        result = update_document_requirement_record(
            requirement=instance,
            cleaned_data=self.cleaned_data,
        )
        return result.requirement


class DocumentRequirementAddForm(forms.Form):
    name = forms.CharField(
        label=_('Название документа'),
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    def __init__(self, *args, purpose: str | None = None, **kwargs):
        self.purpose = purpose
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs.setdefault('autofocus', 'autofocus')

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        self.cleaned_data['slug'] = build_document_requirement_code(
            purpose=self.purpose,
            name=name,
        )
        return name

    def save(self):
        if not hasattr(self, 'cleaned_data'):
            raise RuntimeError("Call is_valid() before save()")
        result = create_document_requirement_for_purpose(
            purpose=self.purpose,
            name=self.cleaned_data['name'],
            slug=self.cleaned_data['slug'],
        )
        return result.requirement


class DocumentChecklistForm(forms.Form):
    required_documents = forms.MultipleChoiceField(
        label=_('Необходимые документы'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        choices=DocumentType.choices,
    )

    def __init__(self, *args, purpose: str | None = None, **kwargs):
        self.purpose = purpose
        super().__init__(*args, **kwargs)
        existing_requirements = list(
            DocumentRequirement.objects.filter(application_purpose=self.purpose)
            .order_by('position', 'id')
        )

        choices = []
        
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
            fallback_docs = get_fallback_document_checklist(self.purpose)
            if fallback_docs:
                choices.extend([doc for doc in fallback_docs if doc[0] not in INTERNAL_DOCS])
            else:
                choices.extend([choice for choice in DocumentType.choices if choice[0] not in INTERNAL_DOCS])

        self.fields['required_documents'].choices = choices

        if 'required_documents' not in self.initial:
            self.initial['required_documents'] = self._initial_documents()

    @staticmethod
    def _label_for_code(code: str) -> str:
        return _label_for_document_type(code)

    def _initial_documents(self):
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

        fallback_docs = get_fallback_document_checklist(self.purpose)
        if fallback_docs:
            return [code for code, _ in fallback_docs if code not in INTERNAL_DOCS]
        return []

    def save(self) -> int:
        result = sync_document_checklist_for_purpose(
            purpose=self.purpose,
            selected_codes=self.cleaned_data.get('required_documents', []),
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
