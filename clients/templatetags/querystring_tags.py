from __future__ import annotations

from typing import Any

from django import template
from django.http import QueryDict

register = template.Library()


@register.simple_tag(takes_context=True)
def querystring_replace(context: dict[str, Any], **kwargs: Any) -> str:
    request = context.get("request")
    query: QueryDict = request.GET.copy() if request is not None else QueryDict(mutable=True)
    for key, value in kwargs.items():
        if value is None or value == "":
            query.pop(key, None)
        else:
            query[key] = str(value)
    encoded = query.urlencode()
    return f"?{encoded}" if encoded else "?"
