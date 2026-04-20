# clients/apps.py

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


def _compile_translations():
    """Compile translation catalogs so document names render in all locales.

    Some environments lack gettext binaries and cannot rely on compiled ``.mo``
    files being present. Compiling at app startup (with a pure-Python fallback)
    keeps translations available without shipping binary assets.
    """

    from django.conf import settings

    if not getattr(settings, "AUTO_COMPILE_TRANSLATIONS_ON_STARTUP", False):
        return

    try:
        from legalize_site.utils.i18n import compile_message_catalogs
    except ImportError:
        logger.warning("Translation auto-compile skipped because i18n utilities are unavailable.")
        return

    try:
        compile_message_catalogs()
    except Exception:
        # Avoid failing app initialization if compilation is not possible; in
        # that case untranslated strings will surface instead of crashing.
        logger.exception("Translation auto-compile failed during app startup.")


class ClientsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'clients'

    def ready(self):
        # Этот импорт для регистрации сигналов
        import clients.signals
        _compile_translations()
