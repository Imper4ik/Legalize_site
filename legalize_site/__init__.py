"""Project package initialization hooks."""

from __future__ import annotations

from contextlib import suppress

with suppress(Exception):
    # ``Engine.default_builtins`` is consulted whenever a new Django template
    # engine instance is created. By appending the compat path here we guarantee
    # the legacy tags stay registered even if another settings module builds its
    # own engine without explicitly opting-in via ``OPTIONS['builtins']``.
    from django.template.engine import Engine

    builtin_path = "legalize_site.templatetags.i18n_compat"
    if builtin_path not in Engine.default_builtins:
        Engine.default_builtins.append(builtin_path)

with suppress(Exception):
    # Import project specific system checks so they register with Django's
    # checks framework as soon as the package is loaded.
    import legalize_site.checks  # noqa: F401  (imported for side effects)
