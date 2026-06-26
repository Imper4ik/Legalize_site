from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from clients.models import (
    Client,
    Company,
    EmailLog,
)
from clients.services.calculator import CURRENCY_EUR, CURRENCY_PLN

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
User = get_user_model()


class MassEmailForm(forms.Form):
    subject = forms.CharField(
        label=_("Тема письма"),
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _("Например: Важное обновление")})
    )
    message = forms.CharField(
        label=_("Текст письма"),
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 6})
    )
    company = forms.ModelChoiceField(
        queryset=Company.objects.all(),
        label=_("Фильтр по Компании"),
        required=False,
        empty_label=_("Все компании"),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    status = forms.ChoiceField(
        label=_("Фильтр по Статусу"),
        required=False,
        choices=[('', _("Все статусы"))] + list(Client.STATUS_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class CalculatorForm(forms.Form):
    total_end_date = forms.DateField(
        input_formats=['%d-%m-%Y'],
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('дд-мм-гггг')}),
    )
    tuition_fee = forms.DecimalField(min_value=0, decimal_places=2, max_digits=10)
    tuition_currency = forms.ChoiceField(choices=((CURRENCY_PLN, 'PLN'), (CURRENCY_EUR, 'EUR')))
    fee_type = forms.ChoiceField(
        choices=(('per_month', 'per_month'), ('per_semester', 'per_semester'), ('per_year', 'per_year')),
        required=False,
    )
    months_in_period = forms.IntegerField(min_value=1)
    rent_and_bills = forms.DecimalField(min_value=0, decimal_places=2, max_digits=10)
    rent_currency = forms.ChoiceField(choices=((CURRENCY_PLN, 'PLN'), (CURRENCY_EUR, 'EUR')))
    num_people = forms.IntegerField(min_value=1)
    has_border = forms.BooleanField(required=False)
    basis_of_stay = forms.ChoiceField(
        choices=(('student', _('Студент')), ('family_reunification', _('Воссоединение семьи'))),
        initial='student',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


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
