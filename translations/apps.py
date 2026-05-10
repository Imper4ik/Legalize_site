from __future__ import annotations

import logging
from typing import Any

from django.apps import AppConfig
from django.utils import translation

logger = logging.getLogger(__name__)

def patch_translations() -> None:
    """
    Perform a deep monkey-patch of Django's translation system
    to wrap all gettext calls in our markers for the Translation Studio.
    """
    if hasattr(translation, '_studio_patched'):
        return

    from django.utils.translation import trans_real

    # 1. Patch the main translation proxy
    if not hasattr(translation, '_original_gettext'):
        setattr(translation, '_original_gettext', translation.gettext)

        def wrapped_gettext(message: Any) -> Any:
            original = getattr(translation, '_original_gettext')
            result = original(message)
            if getattr(translation, '_studio_active', False) and message and not str(message).startswith('[[i18n:'):
                return f"[[i18n:{message}]]{result}[[/i18n]]"
            return result

        setattr(translation, 'gettext', wrapped_gettext)

    # 2. Patch trans_real for more direct access (used by translate/blocktrans tags)
    if not hasattr(trans_real, '_original_gettext'):
        setattr(trans_real, '_original_gettext', trans_real.gettext)

        def wrapped_real_gettext(message: Any) -> Any:
            original = getattr(trans_real, '_original_gettext')
            result = original(message)
            if getattr(translation, '_studio_active', False) and message and not str(message).startswith('[[i18n:'):
                return f"[[i18n:{message}]]{result}[[/i18n]]"
            return result

        setattr(trans_real, 'gettext', wrapped_real_gettext)

    # 3. Patch DjangoTranslation.gettext (the actual translator class)
    if hasattr(trans_real, 'DjangoTranslation'):
        dt_class = trans_real.DjangoTranslation
        if not hasattr(dt_class, '_original_gettext'):
            setattr(dt_class, '_original_gettext', dt_class.gettext)

            def wrapped_class_gettext(self: Any, message: Any) -> Any:
                original = getattr(self, '_original_gettext')
                result = original(message)
                if getattr(translation, '_studio_active', False) and message and not str(message).startswith('[[i18n:'):
                    return f"[[i18n:{message}]]{result}[[/i18n]]"
                return result

            setattr(dt_class, 'gettext', wrapped_class_gettext)

    # 4. Patch plural form functions (ngettext) to ensure plurals are wrapped as well
    if hasattr(translation, 'ngettext') and not hasattr(translation, '_original_ngettext'):
        setattr(translation, '_original_ngettext', translation.ngettext)

        def wrapped_ngettext(singular: Any, plural: Any, number: Any) -> Any:
            original = getattr(translation, '_original_ngettext')
            result = original(singular, plural, number)
            if getattr(translation, '_studio_active', False) and singular and not str(singular).startswith('[[i18n:'):
                return f"[[i18n:{singular}]]{result}[[/i18n]]"
            return result

        setattr(translation, 'ngettext', wrapped_ngettext)

    if not hasattr(trans_real, '_original_ngettext') and hasattr(trans_real, 'ngettext'):
        setattr(trans_real, '_original_ngettext', trans_real.ngettext)

        def wrapped_real_ngettext(singular: Any, plural: Any, number: Any) -> Any:
            original = getattr(trans_real, '_original_ngettext')
            result = original(singular, plural, number)
            if getattr(translation, '_studio_active', False) and singular and not str(singular).startswith('[[i18n:'):
                return f"[[i18n:{singular}]]{result}[[/i18n]]"
            return result

        setattr(trans_real, 'ngettext', wrapped_real_ngettext)

    if hasattr(trans_real, 'DjangoTranslation'):
        dt_class = trans_real.DjangoTranslation
        if not hasattr(dt_class, '_original_ngettext') and hasattr(dt_class, 'ngettext'):
            setattr(dt_class, '_original_ngettext', dt_class.ngettext)

            def wrapped_class_ngettext(self: Any, singular: Any, plural: Any, number: Any) -> Any:
                original = getattr(self, '_original_ngettext')
                result = original(singular, plural, number)
                if getattr(translation, '_studio_active', False) and singular and not str(singular).startswith('[[i18n:'):
                    return f"[[i18n:{singular}]]{result}[[/i18n]]"
                return result

            setattr(dt_class, 'ngettext', wrapped_class_ngettext)

    setattr(translation, '_studio_patched', True)
    logger.info("Successfully performed deep patch on Django translation system.")

def patch_db_override() -> None:
    """Patch Django's trans_real.gettext to apply DB overrides."""
    from django.utils.translation import trans_real
    from .runtime import apply_db_override

    if hasattr(trans_real, '_db_patched'):
        return

    orig_gettext = trans_real.gettext

    def db_wrapped_gettext(message: Any) -> Any:
        translated = orig_gettext(message)
        return apply_db_override(str(message), translated)

    trans_real.gettext = db_wrapped_gettext
    trans_real._db_patched = True
    logger.info("Successfully patched Django translation system with DB overrides.")


class TranslationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'translations'

    def ready(self) -> None:
        from django.conf import settings
        
        if getattr(settings, 'TRANSLATION_DB_OVERRIDES_ENABLED', True):
            patch_db_override()

        use_wrap = getattr(settings, 'TRANSLATION_STUDIO_SERVER_WRAP', False)

        if use_wrap:
            patch_translations()
            return

        # If the system was patched previously (hot-reload during dev), try
        # to restore original functions so markers are not emitted for users.
        try:
            from django.utils import translation as _translation
            from django.utils.translation import trans_real as _trans_real

            if hasattr(_translation, '_original_gettext'):
                setattr(_translation, 'gettext', getattr(_translation, '_original_gettext'))
                delattr(_translation, '_original_gettext')

            if hasattr(_trans_real, '_original_gettext'):
                setattr(_trans_real, 'gettext', getattr(_trans_real, '_original_gettext'))
                delattr(_trans_real, '_original_gettext')

            if hasattr(_trans_real, 'DjangoTranslation'):
                dt_class = _trans_real.DjangoTranslation
                if hasattr(dt_class, '_original_gettext'):
                    setattr(dt_class, 'gettext', getattr(dt_class, '_original_gettext'))
                    delattr(dt_class, '_original_gettext')

            if hasattr(_translation, '_original_ngettext'):
                setattr(_translation, 'ngettext', getattr(_translation, '_original_ngettext'))
                delattr(_translation, '_original_ngettext')

            if hasattr(_trans_real, '_original_ngettext'):
                setattr(_trans_real, 'ngettext', getattr(_trans_real, '_original_ngettext'))
                delattr(_trans_real, '_original_ngettext')

            if hasattr(_trans_real, 'DjangoTranslation'):
                dt_class = _trans_real.DjangoTranslation
                if hasattr(dt_class, '_original_ngettext'):
                    setattr(dt_class, 'ngettext', getattr(dt_class, '_original_ngettext'))
                    delattr(dt_class, '_original_ngettext')

            if hasattr(_translation, '_studio_patched'):
                delattr(_translation, '_studio_patched')

            # Ensure no stale studio flag is present
            if hasattr(_translation, '_studio_active'):
                setattr(_translation, '_studio_active', False)

            logger.info("Translation Studio server-wrap disabled; originals restored if present.")
        except Exception:
            # Fail silently; we don't want to crash app startup for this cleanup
            logger.exception("Error while attempting to restore original translation functions")
