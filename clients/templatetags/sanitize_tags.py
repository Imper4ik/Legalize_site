"""Template filters for safe HTML output of user-generated content."""
from __future__ import annotations

from typing import Any

from django import template
from django.utils.safestring import SafeString, mark_safe

from clients.security.sanitizer import sanitize_user_html

register = template.Library()


@register.filter(name="sanitize_html")
def sanitize_html(value: Any) -> SafeString:
    """Sanitize HTML on output, allowing only safe formatting tags.

    Usage in templates::

        {% load sanitize_tags %}
        {{ client.notes|sanitize_html }}

    This filter should be used instead of ``|safe`` for any user-generated
    HTML content.  It strips all tags except the formatting whitelist and
    marks the result as safe for rendering.
    """
    cleaned = sanitize_user_html(value)
    # The string has just been sanitized with a strict allowlist.
    return mark_safe(cleaned)  # nosec  # noqa: S308
