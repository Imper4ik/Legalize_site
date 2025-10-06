"""Backward-compatible alias for the legacy ``form_filters`` template tag library."""

from django import template

from .portal_filters import add_class, add_placeholder

register = template.Library()

register.filter("add_class", add_class)
register.filter("add_placeholder", add_placeholder)

