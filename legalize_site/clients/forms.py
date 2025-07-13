# clients/forms.py

from django import forms
from .models import Client, Document, Payment


class ClientForm(forms.ModelForm):
    # Explicitly define date fields for custom formatting and widgets
    legal_basis_end_date = forms.DateField(
        label="Дата окончания основания", required=False, input_formats=['%d.%m.%Y'],
        widget=forms.TextInput(attrs={'placeholder': 'дд.мм.гггг', 'data-input': ''})
    )
    fingerprints_date = forms.DateField(
        label="Дата сдачи отпечатков", required=False, input_formats=['%d.%m.%Y'],
        widget=forms.TextInput(attrs={'placeholder': 'дд.мм.гггг', 'data-input': ''})
    )
    submission_date = forms.DateField(
        label="Дата подачи (Złożone)", required=False, input_formats=['%d.%m.%Y'],
        widget=forms.TextInput(attrs={'placeholder': 'дд.мм.гггг', 'data-input': ''})
    )

    class Meta:
        model = Client
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Apply Bootstrap class to all fields
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})

        # If this is a new client, hide fields that are not yet relevant
        if not self.instance.pk:
            if 'case_number' in self.fields:
                del self.fields['case_number']
            if 'fingerprints_date' in self.fields:
                del self.fields['fingerprints_date']
            if 'status' in self.fields:
                del self.fields['status']
            if 'submission_date' in self.fields:
                del self.fields['submission_date']


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['file']


class PaymentForm(forms.ModelForm):
    payment_date = forms.DateField(
        label="Дата оплаты", required=False, input_formats=['%d.%m.%Y'],
        widget=forms.TextInput(attrs={'placeholder': 'дд.мм.гггг', 'data-input': ''})
    )
    due_date = forms.DateField(
        label="Оплатить до", required=False, input_formats=['%d.%m.%Y'],
        widget=forms.TextInput(attrs={'placeholder': 'дд.мм.гггг', 'data-input': ''})
    )

    class Meta:
        model = Payment
        fields = ['service_description', 'total_amount', 'amount_paid', 'status', 'payment_date', 'due_date',
                  'payment_method', 'transaction_id']
        widgets = {
            'service_description': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                field.widget.attrs.update({'class': 'form-control'})