from django import forms
from .models import Client, Document, Payment


class ClientForm(forms.ModelForm):
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
        # ИСПРАВЛЕНО: Добавлены виджеты для всех полей, чтобы обеспечить единый стиль
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
            # Используем type="text" и плейсхолдер, чтобы flatpickr работал корректно
            'legal_basis_end_date': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'дд.мм.гггг'}),
            'submission_date': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'дд.мм.гггг'}),
            'fingerprints_date': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'дд.мм.гггг'}),
            'employer_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['file']


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = [
            'service_description', 'total_amount', 'amount_paid', 'status',
            'payment_method', 'payment_date', 'due_date', 'transaction_id'
        ]
        # Здесь тоже меняем виджеты на TextInput для единообразия с flatpickr
        widgets = {
            'payment_date': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'дд.мм.гггг'}),
            'due_date': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'дд.мм.гггг'}),
            'service_description': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'total_amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'amount_paid': forms.NumberInput(attrs={'class': 'form-control'}),
            'transaction_id': forms.TextInput(attrs={'class': 'form-control'}),
        }
