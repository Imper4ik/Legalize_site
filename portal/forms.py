from clients.models import Client, Document


# portal/forms.py
from django import forms
from .models import ClientApplication


class ClientApplicationForm(forms.ModelForm):
    class Meta:
        model = ClientApplication
        # Включаем все поля, кроме пользователя (он будет назначен автоматически)
        exclude = ['user']

        # Можно добавить виджеты для красивого отображения полей
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'last_entry_date': forms.DateInput(attrs={'type': 'date'}),
            'purpose_of_stay': forms.Select(attrs={'class': 'form-control'}),
            # Добавьте другие виджеты по аналогии для остальных полей
        }


class CustomSignupForm(forms.Form):
    first_name = forms.CharField(max_length=100, label='Имя')
    last_name = forms.CharField(max_length=100, label='Фамилия')

    def signup(self, request, user):
        """
        Этот метод вызывается allauth после создания базового пользователя.
        Здесь мы сохраняем дополнительные данные и создаем/обновляем профиль клиента.
        """
        # 1. Сохраняем имя и фамилию в стандартную модель User
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.save()

        # 2. Обновляем уже существующего клиента по email.
        #    Создание новой записи без обязательных полей (телефон, гражданство и т.д.)
        #    вызывало ошибки IntegrityError, поэтому просто связываем существующий профиль.
        client = Client.objects.filter(email=user.email).first()
        if client:
            fields_to_update = []

            if client.user != user:
                client.user = user
                fields_to_update.append('user')

            if not client.first_name and user.first_name:
                client.first_name = user.first_name
                fields_to_update.append('first_name')

            if not client.last_name and user.last_name:
                client.last_name = user.last_name
                fields_to_update.append('last_name')

            if not client.status:
                client.status = 'new'
                fields_to_update.append('status')

            if fields_to_update:
                client.save(update_fields=fields_to_update)
        return user


# --- Форма для редактирования профиля ---
# Эта форма используется на странице /portal/profile/edit/
# Она использует правильные имена полей из вашей модели Client.

class ProfileEditForm(forms.ModelForm):
    class Meta:
        model = Client
        # Указываем ТОЛЬКО те поля, которые пользователь может изменять сам.
        fields = [
            'first_name',
            'last_name',
            'citizenship',
            'phone',
            'email',
            'passport_num',
            'basis_of_stay',
            'legal_basis_end_date',
            'notes'
        ]

        # Настраиваем виджеты, чтобы поля выглядели красиво
        widgets = {
            'legal_basis_end_date': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'citizenship': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'passport_num': forms.TextInput(attrs={'class': 'form-control'}),
            'basis_of_stay': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }


# --- НОВАЯ ФОРМА ---
class DocumentPortalUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['file']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control form-control-sm'})
        }
