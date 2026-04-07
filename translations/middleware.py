import re
from django.utils import translation

# TAG_PATTERN is for matching [[i18n:Key]]Text[[/i18n]] in final HTML
TAG_PATTERN = re.compile(r'\[\[i18n:(?P<msgid>.*?)\]\](?P<text>.*?)\[\[/i18n\]\]', re.DOTALL | re.IGNORECASE)

class TranslationStudioMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # Patching is now handled in apps.py ready() for better coverage

    def __call__(self, request):
        # 1. Determine if Studio Mode is active
        # Visible to superusers with session flag or 'studio' in GET
        is_superuser = request.user.is_authenticated and request.user.is_superuser
        studio_active = is_superuser and (request.session.get('studio_mode') or 'studio' in request.GET)
        
        # 2. Store state globally for current thread (gettext monkey-patches use this)
        translation._studio_active = studio_active
        
        response = self.get_response(request)

        # IMPORTANT: previous approach attempted to convert server-side markers
        # ([[i18n:...]]...[[/i18n]]) into HTML <span> elements here. That naive
        # string replacement could accidentally inject markup inside HTML
        # attributes (breaking inputs/placeholders). To avoid corrupting
        # attributes we now leave the raw markers in the response and let the
        # client-side overlay (translation_overlay.js) scan the DOM and safely
        # replace text nodes with editable spans. The overlay only runs for
        # superusers when Studio Mode is active, so end users won't see markers.
        #
        return response
