from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Document, Submission


class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ['name', 'status']

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if not name:
            raise forms.ValidationError(_('Название не может быть пустым'))
        return name


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['title', 'status', 'file_path']

    def clean_title(self):
        title = self.cleaned_data['title'].strip()
        if not title:
            raise forms.ValidationError(_('Название документа обязательно'))
        return title

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get('status')
        file_path = cleaned.get('file_path')

        if status and status != Document.Status.NOT_UPLOADED and not file_path:
            self.add_error('file_path', _('Файл обязателен для выбранного статуса'))
        return cleaned
