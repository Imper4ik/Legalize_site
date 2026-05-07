from __future__ import annotations

from typing import Any

from django import template

register = template.Library()

@register.filter
def get_by_type(documents: Any, doc_type: str) -> Any:
    if hasattr(documents, "filter"):
        return documents.filter(document_type=doc_type).first()
    return None
