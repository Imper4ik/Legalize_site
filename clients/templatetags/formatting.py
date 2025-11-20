from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def format_currency(value):
    try:
        number = Decimal(value)
    except (TypeError, InvalidOperation):
        return ""
    formatted = f"{number:,.2f}".replace(",", " ")
    return formatted


@register.filter
def format_date(value, fmt: str = "%d-%m-%Y"):
    if isinstance(value, (date, datetime)):
        return value.strftime(fmt)
    return value
