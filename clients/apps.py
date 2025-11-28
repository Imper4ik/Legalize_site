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

    try:
        from legalize_site.utils.i18n import compile_message_catalogs
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Translation compilation unavailable: %s", exc)
        return

    try:
        compile_message_catalogs()
    except Exception as exc:  # pragma: no cover - defensive
        # Avoid failing app initialization if compilation is not possible; in
        # that case untranslated strings will surface instead of crashing.
        logger.warning("Could not compile translations at startup: %s", exc)


class ClientsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'clients'

    def ready(self):
        # Этот импорт для регистрации сигналов
        import clients.signals
        _compile_translations()
