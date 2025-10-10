"""Compatibility aliases for legacy translation template tags."""

from django import template
from django.templatetags.i18n import do_block_translate, do_translate


register = template.Library()

# Support legacy `{% blocktranslate %}` usage by mapping it to Django's
# built-in `{% blocktrans %}` implementation. This lets older templates keep
# working while new ones can use the canonical tag.
register.tag("blocktranslate", do_block_translate)

# Some legacy templates may still rely on `{% translate %}` as an alias for
# `{% trans %}`. Django already provides `translate`, but registering it here
# ensures consistent availability when the compat library is loaded as a
# builtin.
register.tag("translate", do_translate)
