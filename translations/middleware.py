import re
from django.conf import settings
from django.urls import reverse
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
        if studio_active and self._path_allowed(request.path):
            self._inject_overlay_script(response)

        return response

    @staticmethod
    def _inject_overlay_script(response):
        if getattr(response, "streaming", False):
            return

        content_type = response.get("Content-Type", "")
        if "text/html" not in content_type.lower():
            return

        try:
            content = response.content.decode("utf-8")
        except Exception:
            return

        script_src = "/static/translations/js/translation_overlay.js"
        if script_src in content:
            return

        dashboard_url = reverse("translations:dashboard")
        update_url = reverse("translations:update_api")
        get_url = reverse("translations:get_api")
        scan_url = reverse("translations:scan_api")
        config_script = (
            "<script>"
            f"window.__studioOverlayConfig={{dashboardUrl:{dashboard_url!r},updateUrl:{update_url!r},getUrl:{get_url!r},scanUrl:{scan_url!r}}};"
            "</script>"
        )
        script_tag = f'{config_script}<script src="{script_src}" defer></script>'
        lower_content = content.lower()
        body_close_idx = lower_content.rfind("</body>")
        if body_close_idx == -1:
            return

        updated = content[:body_close_idx] + script_tag + content[body_close_idx:]
        response.content = updated.encode("utf-8")

    @staticmethod
    def _path_allowed(path: str) -> bool:
        include_prefixes = getattr(settings, "STUDIO_OVERLAY_INCLUDE_PREFIXES", ())
        exclude_prefixes = getattr(
            settings,
            "STUDIO_OVERLAY_EXCLUDE_PREFIXES",
            ("/static/", "/media/"),
        )

        if include_prefixes:
            if not any(path.startswith(prefix) for prefix in include_prefixes):
                return False

        if exclude_prefixes and any(path.startswith(prefix) for prefix in exclude_prefixes):
            return False

        return True
