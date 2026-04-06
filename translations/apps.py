from django.apps import AppConfig
from django.utils import translation
import logging

logger = logging.getLogger(__name__)

def patch_translations():
    """
    Perform a deep monkey-patch of Django's translation system 
    to wrap all gettext calls in our markers for the Translation Studio.
    """
    if hasattr(translation, '_studio_patched'):
        return

    from django.utils.translation import trans_real
    
    # 1. Patch the main translation proxy
    if not hasattr(translation, '_original_gettext'):
        translation._original_gettext = translation.gettext
        
        def wrapped_gettext(message):
            result = translation._original_gettext(message)
            if getattr(translation, '_studio_active', False) and message and not message.startswith('[[i18n:'):
                return f"[[i18n:{message}]]{result}[[/i18n]]"
            return result
        
        translation.gettext = wrapped_gettext

    # 2. Patch trans_real for more direct access (used by translate/blocktrans tags)
    if not hasattr(trans_real, '_original_gettext'):
        trans_real._original_gettext = trans_real.gettext
        
        def wrapped_real_gettext(message):
            result = trans_real._original_gettext(message)
            if getattr(translation, '_studio_active', False) and message and not message.startswith('[[i18n:'):
                return f"[[i18n:{message}]]{result}[[/i18n]]"
            return result
        
        trans_real.gettext = wrapped_real_gettext

    # 3. Patch DjangoTranslation.gettext (the actual translator class)
    if hasattr(trans_real, 'DjangoTranslation'):
        if not hasattr(trans_real.DjangoTranslation, '_original_gettext'):
            trans_real.DjangoTranslation._original_gettext = trans_real.DjangoTranslation.gettext
            
            def wrapped_class_gettext(self, message):
                result = self._original_gettext(message)
                if getattr(translation, '_studio_active', False) and message and not message.startswith('[[i18n:'):
                    return f"[[i18n:{message}]]{result}[[/i18n]]"
                return result
            
            trans_real.DjangoTranslation.gettext = wrapped_class_gettext

    # 4. Patch plural form functions (ngettext) to ensure plurals are wrapped as well
    if hasattr(translation, 'ngettext') and not hasattr(translation, '_original_ngettext'):
        translation._original_ngettext = translation.ngettext

        def wrapped_ngettext(singular, plural, number):
            result = translation._original_ngettext(singular, plural, number)
            if getattr(translation, '_studio_active', False) and singular and not singular.startswith('[[i18n:'):
                return f"[[i18n:{singular}]]{result}[[/i18n]]"
            return result

        translation.ngettext = wrapped_ngettext

    if not hasattr(trans_real, '_original_ngettext') and hasattr(trans_real, 'ngettext'):
        trans_real._original_ngettext = trans_real.ngettext

        def wrapped_real_ngettext(singular, plural, number):
            result = trans_real._original_ngettext(singular, plural, number)
            if getattr(translation, '_studio_active', False) and singular and not singular.startswith('[[i18n:'):
                return f"[[i18n:{singular}]]{result}[[/i18n]]"
            return result

        trans_real.ngettext = wrapped_real_ngettext

    if hasattr(trans_real, 'DjangoTranslation'):
        if not hasattr(trans_real.DjangoTranslation, '_original_ngettext') and hasattr(trans_real.DjangoTranslation, 'ngettext'):
            trans_real.DjangoTranslation._original_ngettext = trans_real.DjangoTranslation.ngettext
            
            def wrapped_class_ngettext(self, singular, plural, number):
                result = self._original_ngettext(singular, plural, number)
                if getattr(translation, '_studio_active', False) and singular and not singular.startswith('[[i18n:'):
                    return f"[[i18n:{singular}]]{result}[[/i18n]]"
                return result
            
            trans_real.DjangoTranslation.ngettext = wrapped_class_ngettext

    translation._studio_patched = True
    logger.info("Successfully performed deep patch on Django translation system.")

class TranslationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'translations'

    def ready(self):
        # Server-side wrapping of gettext results can leak markers into HTML
        # when not carefully controlled. By default we disable the deep
        # monkey-patch and rely on the client-side overlay + scan API to
        # safely create editable spans in the browser. If you really need
        # server-side wrapping, set `TRANSLATION_STUDIO_SERVER_WRAP = True`
        # in your settings.
        from django.conf import settings
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
                _translation.gettext = _translation._original_gettext
                delattr(_translation, '_original_gettext')

            if hasattr(_trans_real, '_original_gettext'):
                _trans_real.gettext = _trans_real._original_gettext
                delattr(_trans_real, '_original_gettext')

            if hasattr(_trans_real, 'DjangoTranslation') and hasattr(_trans_real.DjangoTranslation, '_original_gettext'):
                _trans_real.DjangoTranslation.gettext = _trans_real.DjangoTranslation._original_gettext
                delattr(_trans_real.DjangoTranslation, '_original_gettext')

            if hasattr(_translation, '_original_ngettext'):
                _translation.ngettext = _translation._original_ngettext
                delattr(_translation, '_original_ngettext')

            if hasattr(_trans_real, '_original_ngettext'):
                _trans_real.ngettext = _trans_real._original_ngettext
                delattr(_trans_real, '_original_ngettext')

            if hasattr(_trans_real, 'DjangoTranslation') and hasattr(_trans_real.DjangoTranslation, '_original_ngettext'):
                _trans_real.DjangoTranslation.ngettext = _trans_real.DjangoTranslation._original_ngettext
                delattr(_trans_real.DjangoTranslation, '_original_ngettext')

            if hasattr(_translation, '_studio_patched'):
                delattr(_translation, '_studio_patched')

            # Ensure no stale studio flag is present
            if hasattr(_translation, '_studio_active'):
                _translation._studio_active = False

            logger.info("Translation Studio server-wrap disabled; originals restored if present.")
        except Exception:
            # Fail silently; we don't want to crash app startup for this cleanup
            logger.exception("Error while attempting to restore original translation functions")
