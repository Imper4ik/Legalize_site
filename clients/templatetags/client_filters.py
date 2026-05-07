# clients/templatetags/client_filters.py
from __future__ import annotations

from typing import Any

from django import template

register = template.Library()

@register.filter(name='add_attr')
def add_attr(field: Any, css: str) -> Any:
    attrs = {}
    definition = css.split(',')

    for d in definition:
        if ':' in d:
            key, val = d.split(':')
            attrs[key.strip()] = val.strip()

    if hasattr(field, "as_widget"):
        return field.as_widget(attrs=attrs)
    return field