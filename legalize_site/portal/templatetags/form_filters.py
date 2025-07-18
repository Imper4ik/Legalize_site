from django import template

register = template.Library()

@register.filter(name='add_class')
def add_class(field, css_class):
    """Adds a CSS class to the form field's widget."""
    # This modifies the widget's attributes but does not render it
    widget_attrs = field.field.widget.attrs
    existing_classes = widget_attrs.get('class', '')
    widget_attrs['class'] = f'{existing_classes} {css_class}'.strip()
    # Return the field object itself to allow for chaining
    return field

@register.filter(name='add_placeholder')
def add_placeholder(field, placeholder_text):
    """Adds a placeholder attribute to the form field's widget."""
    # This modifies the widget's attributes
    field.field.widget.attrs['placeholder'] = placeholder_text
    # Return the field object itself
    return field