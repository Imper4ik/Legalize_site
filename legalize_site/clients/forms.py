# clients/forms.py

from django import forms
from .models import Client, Document

class ClientForm(forms.ModelForm):
    # Явно переопределяем поле для даты
    legal_basis_end_date = forms.DateField(
        label="Дата окончания основания",
        required=False,  # Поле не обязательное
        # Указываем, что мы ожидаем дату в этом формате
        input_formats=['%d.%m.%Y'],
        # Используем обычное текстовое поле, чтобы наш календарь мог с ним работать
        widget=forms.TextInput(attrs={'placeholder': 'дд.мм.гггг'})
    )

    class Meta:
        model = Client
        fields = '__all__' # Включаем все поля модели

    # Этот метод добавит красивые стили Bootstrap ко всем полям
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})

# Эта форма нужна для загрузки файлов
class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['file']