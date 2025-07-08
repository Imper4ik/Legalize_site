# clients/forms.py

from django import forms
from .models import Client, Document

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = '__all__' # Просто используем все поля из модели

    # Этот метод просто добавляет стили Bootstrap
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            # Пропускаем поле с датой, так как мы его стилизуем вручную
            if field_name != 'legal_basis_end_date':
                field.widget.attrs.update({'class': 'form-control'})

# Эта форма для загрузки файлов
class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['file']