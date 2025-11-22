from django import forms
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

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


class DocumentChecklistForm(forms.Form):
    required_documents = forms.MultipleChoiceField(
        label=_('Необходимые документы'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        choices=DocumentType.choices,
    )
    new_document_name = forms.CharField(
        label=_('Добавить новый документ'),
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Например: Подтверждение проживания')}),
    )

    def __init__(self, *args, purpose: str | None = None, **kwargs):
        self.purpose = purpose
        super().__init__(*args, **kwargs)
        self.fields['required_documents'].choices = self._choices()
        self._default_labels = {choice.value: choice.label for choice in DocumentType}
        self._existing_labels = dict(
            DocumentRequirement.objects.filter(application_purpose=self.purpose).values_list('document_type', 'custom_name')
        )

        for code, label in self.fields['required_documents'].choices:
            field_name = self._label_field_name(code)
            initial_value = self._existing_labels.get(code) or self._default_labels.get(code) or label
            self.fields[field_name] = forms.CharField(
                required=False,
                label='',
                initial=initial_value,
                widget=forms.TextInput(
                    attrs={
                        'class': 'form-control form-control-sm',
                        'placeholder': _('Название документа'),
                    }
                ),
            )

        if 'required_documents' not in self.initial:
            self.initial['required_documents'] = self._initial_documents()

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

    def _choices(self):
        base_choices = list(DocumentType.choices)
        existing = DocumentRequirement.objects.filter(application_purpose=self.purpose)
        seen = {code for code, _ in base_choices}
        for doc in existing:
            if doc.document_type not in seen:
                label = doc.custom_name or doc.document_type.replace('_', ' ').capitalize()
                base_choices.append((doc.document_type, label))
                seen.add(doc.document_type)
        return base_choices

    def _slug_from_name(self, name: str) -> str:
        base = slugify(name, allow_unicode=True).replace('-', '_')
        if not base:
            return ''
        candidate = base
        counter = 1
        while DocumentRequirement.objects.filter(application_purpose=self.purpose, document_type=candidate).exists():
            counter += 1
            candidate = f"{base}_{counter}"
        return candidate

    def save(self) -> int:
        if self.purpose is None:
            return 0

        selected_codes = list(self.cleaned_data.get('required_documents', []))
        new_name = (self.cleaned_data.get('new_document_name') or '').strip()
        custom_labels = {}

        name_fields: dict[str, str] = {}
        for code, _ in self.fields['required_documents'].choices:
            field_name = self._label_field_name(code)
            name_fields[code] = (self.cleaned_data.get(field_name) or '').strip()

        if new_name:
            slug = self._slug_from_name(new_name)
            if slug:
                if slug not in selected_codes:
                    selected_codes.append(slug)
                custom_labels[slug] = new_name

        DocumentRequirement.objects.filter(application_purpose=self.purpose).exclude(
            document_type__in=selected_codes
        ).delete()

        for position, code in enumerate(selected_codes):
            provided_label = name_fields.get(code) or custom_labels.get(code, '')
            base_label = self._default_labels.get(code)
            custom_name = provided_label if provided_label and (base_label is None or provided_label != base_label) else ''
            DocumentRequirement.objects.update_or_create(
                application_purpose=self.purpose,
                document_type=code,
                defaults={'is_required': True, 'position': position, 'custom_name': custom_name},
            )

        return len(selected_codes)

    def _label_field_name(self, code: str) -> str:
        return f"label_{code}"


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