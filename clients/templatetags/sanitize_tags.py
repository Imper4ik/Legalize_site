"""Template filters for safe HTML output of user-generated content."""

import bleach
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

ALLOWED_TAGS = ["b", "strong", "i", "em", "br", "ul", "ol", "li", "p"]


@register.filter(name="sanitize_html")
def sanitize_html(value):
    """Sanitize HTML on output, allowing only safe formatting tags.

    Usage in templates::

        {% load sanitize_tags %}
        {{ client.notes|sanitize_html }}

    This filter should be used instead of ``|safe`` for any user-generated
    HTML content.  It strips all tags except the formatting whitelist and
    marks the result as safe for rendering.
    """
    if not value:
        return ""
    cleaned = bleach.clean(str(value), tags=ALLOWED_TAGS, attributes={}, strip=True)
    return mark_safe(cleaned)  # noqa: S308 — output is sanitized by bleach
