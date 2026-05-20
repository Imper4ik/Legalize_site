from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from clients.models.email import EmailLog

User = get_user_model()


class EmailLogFilterForm(forms.Form):
    status = forms.ChoiceField(
        choices=[("", _("Все статусы"))] + EmailLog.DELIVERY_STATUS_CHOICES,
        required=False,
        label=_("Статус"),
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    date_start = forms.DateField(
        required=False,
        label=_("С даты"),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
    date_end = forms.DateField(
        required=False,
        label=_("По дату"),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
    search = forms.CharField(
        required=False,
        label=_("Поиск"),
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-sm",
                "placeholder": _("Тема или имя клиента..."),
            }
        ),
    )


class StaffActivityFilterForm(forms.Form):
    actor = forms.ModelChoiceField(
        queryset=User.objects.filter(is_staff=True).order_by("email"),
        required=False,
        empty_label=_("Все сотрудники"),
        label=_("Сотрудник"),
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    date_start = forms.DateField(
        required=False,
        label=_("С даты"),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
    date_end = forms.DateField(
        required=False,
        label=_("По дату"),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
