from django import forms
from django.utils.translation import gettext_lazy as _
from django.utils.crypto import get_random_string
from django.utils.text import slugify

from clients.services.calculator import CURRENCY_EUR, CURRENCY_PLN
from .constants import DOCUMENT_CHECKLIST, DocumentType
from .models import Client, Document, DocumentRequirement, Payment


class ClientForm(forms.ModelForm):
    # --- FIXED HERE ---
    # We explicitly define the date fields to make them not required
    # and to specify the correct date format from the calendar.
    legal_basis_end_date = forms.DateField(
        label="Дата окончания основания",
        required=False,
        input_formats=['%d-%m-%Y'],
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'дд-мм-гггг'})
    )
    submission_date = forms.DateField(
        label="Дата подачи (Złożone)",
        required=False,
        input_formats=['%d-%m-%Y'],
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'дд-мм-гггг'})
    )
    fingerprints_date = forms.DateField(
        label="Дата сдачи отпечатков",
        required=False,
        input_formats=['%d-%m-%Y'],
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'дд-мм-гггг'})
    )

    class Meta:
        model = Client
        fields = [
            'first_name', 'last_name', 'email', 'phone', 'citizenship',
            'passport_num', 'case_number', 'application_purpose', 'language',
            'status',
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
            'passport_num': forms.TextInput(attrs={'class': 'form-control'}),
            'case_number': forms.TextInput(attrs={'class': 'form-control'}),
            'application_purpose': forms.Select(attrs={'class': 'form-select'}),
            'language': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'basis_of_stay': forms.TextInput(attrs={'class': 'form-control'}),
            'employer_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['file', 'expiry_date']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control'}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }


class PaymentForm(forms.ModelForm):
    payment_date = forms.DateField(
        required=False,
        input_formats=['%d-%m-%Y', '%Y-%m-%d'],
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    due_date = forms.DateField(
        required=False,
        input_formats=['%d-%m-%Y', '%Y-%m-%d'],
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
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


class DocumentRequirementEditForm(forms.ModelForm):
    class Meta:
        model = DocumentRequirement
        fields = ['custom_name', 'is_required']
        widgets = {
            'custom_name': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'is_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class DocumentRequirementAddForm(forms.Form):
    name = forms.CharField(
        label=_('Название документа'),
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Например: ZUS RCA')}),
    )

    def __init__(self, *args, purpose: str | None = None, **kwargs):
        self.purpose = purpose
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        slug = slugify(name, allow_unicode=True).replace('-', '_')
        if not slug:
            slug = f"custom_doc_{get_random_string(5)}"

        candidate = slug
        while DocumentRequirement.objects.filter(application_purpose=self.purpose, document_type=candidate).exists():
            candidate = f"{slug}_{get_random_string(4)}"

        self.cleaned_data['slug'] = candidate
        return name

    def save(self):
        position = DocumentRequirement.objects.filter(application_purpose=self.purpose).count()
        return DocumentRequirement.objects.create(
            application_purpose=self.purpose,
            document_type=self.cleaned_data['slug'],
            custom_name=self.cleaned_data['name'],
            is_required=True,
            position=position,
        )


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

        existing_codes = {item.document_type for item in existing_requirements}
        choices = []

        for requirement in existing_requirements:
            label = requirement.custom_name or self._label_for_code(requirement.document_type)
            choices.append((requirement.document_type, label))

        for code, label in DocumentType.choices:
            if code not in existing_codes:
                choices.append((code, label))

        self.fields['required_documents'].choices = choices

        if 'required_documents' not in self.initial:
            self.initial['required_documents'] = self._initial_documents()

    @staticmethod
    def _label_for_code(code: str) -> str:
        try:
            return DocumentType(code).label
        except ValueError:
            return code.replace('_', ' ').capitalize()

    def _initial_documents(self):
        existing = (
            DocumentRequirement.objects.filter(application_purpose=self.purpose, is_required=True)
            .order_by('position', 'id')
            .values_list('document_type', flat=True)
        )
        if existing:
            return list(existing)

        for (purpose, _), docs in DOCUMENT_CHECKLIST.items():
            if purpose == self.purpose:
                return [code for code, _ in docs]
        return []

    def save(self) -> int:
        if self.purpose is None:
            return 0

        selected_codes = list(self.cleaned_data.get('required_documents', []))
        selected_positions = {code: pos for pos, code in enumerate(selected_codes)}

        existing = {
            requirement.document_type: requirement
            for requirement in DocumentRequirement.objects.filter(application_purpose=self.purpose)
        }

        for code in selected_codes:
            if code in existing:
                requirement = existing[code]
                requirement.is_required = True
                requirement.position = selected_positions.get(code, requirement.position)
                requirement.save(update_fields=['is_required', 'position'])
            else:
                DocumentRequirement.objects.create(
                    application_purpose=self.purpose,
                    document_type=code,
                    is_required=True,
                    position=selected_positions.get(code, 0),
                )

        for requirement in existing.values():
            if requirement.document_type not in selected_positions and requirement.is_required:
                requirement.is_required = False
                requirement.save(update_fields=['is_required'])

        return len(selected_codes)


class CalculatorForm(forms.Form):
    total_end_date = forms.DateField(
        input_formats=['%d-%m-%Y'],
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'дд-мм-гггг'}),
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