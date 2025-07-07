# clients/forms.py

from django import forms
from .models import Client, Document

class ClientForm(forms.ModelForm):
    # Явно переопределяем поле для даты
    legal_basis_end_date = forms.DateField(
        label="Дата окончания основания",
        required=False,
        input_formats=['%d.%m.%Y'],
        # ИЗМЕНЕНИЕ ЗДЕСЬ: добавляем все нужные атрибуты прямо в виджет
        widget=forms.TextInput(attrs={
            'placeholder': 'дд.мм.гггг',
            'data-input': ''  # Атрибут, который ищет flatpickr
        })
    )

    class Meta:
        model = Client
        fields = '__all__'

    # Этот метод добавляет стили Bootstrap ко всем полям
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})

# Эта форма нужна для загрузки файлов
class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['file']