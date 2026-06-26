from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from clients.models import (
    Client,
    Payment,
    StaffTask,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
User = get_user_model()


class PaymentForm(forms.ModelForm):
    payment_date = forms.DateField(
        required=False,
        input_formats=['%d.%m.%Y', '%d-%m-%Y', '%Y-%m-%d'],
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    due_date = forms.DateField(
        required=False,
        input_formats=['%d.%m.%Y', '%d-%m-%Y', '%Y-%m-%d'],
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    amount_paid = forms.DecimalField(
        required=False,
        initial=0,
        min_value=Decimal("0.00"),
        localize=True,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'})
    )
    total_amount = forms.DecimalField(
        min_value=Decimal("0.00"),
        localize=True,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'})
    )
    status = forms.ChoiceField(
        required=False,
        choices=Payment.PAYMENT_STATUS_CHOICES,
        initial='pending',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Payment
        fields = [
            "service_description",
            "total_amount",
            "amount_paid",
            "status",
            "payment_method",
            "payment_date",
            "due_date",
            "transaction_id",
        ]
        widgets = {
            "service_description": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "payment_method": forms.Select(attrs={"class": "form-select"}),
            "total_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "amount_paid": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "transaction_id": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean_amount_paid(self) -> Decimal:
        return cast(Decimal, self.cleaned_data.get("amount_paid") or Decimal("0.00"))

    def clean(self) -> dict[str, Any]:
        cleaned_data = cast(dict[str, Any], super().clean() or {})
        total = cleaned_data.get("total_amount")
        paid = cleaned_data.get("amount_paid")
        if total is not None and paid is not None and paid > total:
            self.add_error(
                "amount_paid",
                _("Оплаченная сумма не может превышать общую сумму."),
            )
        return cleaned_data

    def __init__(self, *args: Any, client: Client | None = None, case: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Bind client/case so the model's case-first validation can resolve a
        # case for single-case clients and reject ambiguous multi-case input.
        if client is not None:
            self.instance.client = client
        if case is not None:
            self.instance.case = case


class StaffTaskForm(forms.ModelForm):
    due_date = forms.DateField(
        required=False,
        input_formats=['%d.%m.%Y', '%d-%m-%Y', '%Y-%m-%d'],
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )

    class Meta:
        model = StaffTask
        fields = ['title', 'description', 'priority', 'status', 'assignee', 'due_date']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'assignee': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args: Any, client: Client | None = None, case: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if client is not None:
            self.instance.client = client
        if case is not None:
            self.instance.case = case
        user_model = get_user_model()
        staff_qs = user_model.objects.filter(is_staff=True, is_active=True).order_by('email')
        if hasattr(self.fields['assignee'], 'queryset'):
            setattr(self.fields['assignee'], 'queryset', staff_qs)
        self.fields['assignee'].required = False
