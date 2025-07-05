# forms.py
from django import forms
from .models import Document, Client


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['doc_type', 'file', 'is_provided']


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            'first_name',
            'last_name',
            'phone',
            'email',
            'passport_num',
            'legal_basis',
            'legal_basis_end_date',
            'apply_for',
            'language',
            'status',
        ]
        widgets = {
            'legal_basis_end_date': forms.DateInput(attrs={'type': 'date'}),
        }
