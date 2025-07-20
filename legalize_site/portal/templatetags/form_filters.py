from django import template

register = template.Library()

@register.filter(name='add_class')
def add_class(field, css_class):
    """
    Adds a CSS class to the form field's widget.
    This is the safe and correct way to do it.
    """
    if hasattr(field, 'as_widget'):
        return field.as_widget(attrs={'class': css_class})
    return field

@register.filter(name='add_placeholder')
def add_placeholder(field, placeholder_text):
    """Adds a placeholder attribute to the form field's widget."""
    if hasattr(field, 'as_widget'):
        return field.as_widget(attrs={'placeholder': placeholder_text})
    return field