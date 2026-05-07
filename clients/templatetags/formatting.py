from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django import template

register = template.Library()


@register.filter
def format_currency(value: Any) -> str:
    try:
        number = Decimal(value)
    except (TypeError, InvalidOperation):
        return ""
    formatted = f"{number:,.2f}".replace(",", " ")
    return formatted


@register.filter
def format_date(value: Any, fmt: str = "%d-%m-%Y") -> Any:
    if isinstance(value, (date, datetime)):
        return value.strftime(fmt)
    return value
