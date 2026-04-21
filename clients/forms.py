from django import forms
from django.contrib.auth import get_user_model
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from clients.services.calculator import CURRENCY_EUR, CURRENCY_PLN
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
    Client,
    Company,
    Document,
    DocumentRequirement,
    Payment,
    StaffTask,
    get_fallback_document_checklist,
    resolve_document_label,
)

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

    class Meta:
        model = Client
        fields = [
            'first_name', 'last_name', 'email', 'phone', 'citizenship',
            'birth_date', 'passport_num', 'case_number', 'application_purpose', 'language',
            'company', 'status', 'workflow_stage',
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
            'basis_of_stay': forms.TextInput(attrs={'class': 'form-control'}),
            'employer_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

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
