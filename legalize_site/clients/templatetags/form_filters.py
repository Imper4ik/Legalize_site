"""Template filters for enriching form widgets with CSS classes and placeholders."""

from django import template

register = template.Library()


@register.filter(name="add_class")
def add_class(field, css_class):
    """Return the field rendered with an extra CSS class."""
    if hasattr(field, "as_widget"):
        attrs = field.field.widget.attrs.copy() if hasattr(field, "field") else {}
        existing = attrs.get("class", "")
        attrs["class"] = f"{existing} {css_class}".strip()
        return field.as_widget(attrs=attrs)
    return field


@register.filter(name="add_placeholder")
def add_placeholder(field, placeholder_text):
    """Return the field rendered with a placeholder attribute."""
    if hasattr(field, "as_widget"):
        attrs = field.field.widget.attrs.copy() if hasattr(field, "field") else {}
        attrs["placeholder"] = placeholder_text
        return field.as_widget(attrs=attrs)
    return field
