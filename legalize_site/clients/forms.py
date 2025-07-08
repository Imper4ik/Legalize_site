# clients/forms.py

from django import forms
from .models import Client, Document


class ClientForm(forms.ModelForm):
    # Явно определяем поля для дат, чтобы они правильно работали с календарём
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

        # Применяем стили Bootstrap ко всем полям
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})

        # ИЗМЕНЕНИЕ: Мы больше не скрываем поле 'submission_date'
        # Теперь при создании нового клиента будут скрыты только номер дела и статус,
        # так как они присваиваются позже.
        if not self.instance.pk:
            del self.fields['case_number']
            del self.fields['status']
            # Поле fingerprints_date тоже оставляем только для редактирования
            del self.fields['fingerprints_date']

        # Эта форма для загрузки файлов


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['file']