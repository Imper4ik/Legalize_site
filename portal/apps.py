from django.apps import AppConfig
from django.core.signals import setting_changed


def _inject_translation_compatibility():
    """Ensure legacy translation tags are available on every template engine."""

    try:
        from django.template import engines
        from django.template.engine import Engine
    except Exception:
        return

    builtin_path = "legalize_site.templatetags.i18n_compat"

    if builtin_path not in Engine.default_builtins:
        Engine.default_builtins.append(builtin_path)

    for backend in engines.all():
        engine = getattr(backend, "engine", None)
        if engine is None:
            continue

        if builtin_path not in engine.builtins:
            engine.builtins.append(builtin_path)
            engine.template_builtins = engine.get_template_builtins(engine.builtins)


def _on_setting_changed(**kwargs):
    if kwargs.get('setting') == 'TEMPLATES':
        _inject_translation_compatibility()


class PortalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'portal'

    def ready(self):
        _inject_translation_compatibility()
        setting_changed.connect(_on_setting_changed, weak=False)
