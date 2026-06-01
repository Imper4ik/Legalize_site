from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, TYPE_CHECKING

from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import user_passes_test
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.conf import settings

from clients.services.roles import user_has_any_role
from .utils import load_all_translations, save_translation_entry

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

logger = logging.getLogger(__name__)


def can_use_translation_studio(user: AbstractBaseUser | AnonymousUser) -> bool:
    return user.is_authenticated and (
        getattr(user, "is_superuser", False) or user_has_any_role(user, "Admin", "Translator")
    )


@user_passes_test(can_use_translation_studio)
def studio_dashboard(request: HttpRequest) -> HttpResponse:
    """Render the side-by-side translation dashboard."""
    translations = load_all_translations()
    return render(request, 'translations/studio_dashboard.html', {
        'translations': translations,
        'languages': ['ru', 'en', 'pl']
    })


@user_passes_test(can_use_translation_studio)
def update_translation_api(request: HttpRequest) -> JsonResponse:
    """API to save a single translation msgid across all languages."""
    if request.method == 'POST':
        try:
            body = request.body.decode('utf-8') if isinstance(request.body, (bytes, bytearray)) else str(request.body)
            try:
                data = json.loads(body)
            except Exception:
                data = {}

            msgid = data.get('msgid')
            ru = data.get('ru')
            en = data.get('en')
            pl = data.get('pl')
            storage = getattr(settings, 'TRANSLATION_STUDIO_STORAGE', 'database')

            updated_langs = []
            if ru is not None:
                updated_langs.append('ru')
            if en is not None:
                updated_langs.append('en')
            if pl is not None:
                updated_langs.append('pl')

            msgid_hash = hashlib.sha256(str(msgid or '').encode('utf-8')).hexdigest()[:12]
            logger.info(
                'update_translation_api called user=%s msgid_hash=%s langs=%s storage=%s',
                getattr(request.user, 'pk', None),
                msgid_hash,
                updated_langs,
                storage,
            )

            save_translation_entry(msgid, ru=ru, en=en, pl=pl, updated_by=request.user, storage=storage)

            return JsonResponse({
                'status': 'ok',
                'storage': storage,
                'msgid': msgid,
                'updated_languages': updated_langs
            })
        except Exception as e:
            logger.warning(
                'Error in update_translation_api user=%s',
                getattr(request.user, 'pk', None),
            )
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)


@user_passes_test(can_use_translation_studio)
@require_POST
def toggle_studio_mode(request: HttpRequest) -> HttpResponse:
    """Turn on/off the in-context editing spans."""
    current = request.session.get('studio_mode', False)
    next_state = not current
    request.session['studio_mode'] = next_state
    logger.info(
        "Translation Studio mode %s by user=%s referer=%s",
        "ENABLED" if next_state else "DISABLED",
        getattr(request.user, "email", getattr(request.user, "pk", None)),
        request.META.get("HTTP_REFERER"),
    )
    from django.utils.http import url_has_allowed_host_and_scheme
    referer = request.META.get('HTTP_REFERER')
    if referer and not url_has_allowed_host_and_scheme(referer, allowed_hosts={request.get_host()}):
        referer = None
    return redirect(referer or '/')


@user_passes_test(can_use_translation_studio)
def get_translation_api(request: HttpRequest) -> JsonResponse:
    """Fetch all 3 languages for a specific msgid."""
    msgid = request.GET.get('msgid')
    if not msgid:
        return JsonResponse({'status': 'error', 'message': 'Missing msgid'}, status=400)

    translations = load_all_translations()
    entry = next((e for e in translations if e['msgid'] == msgid), None)

    if entry:
        return JsonResponse({'status': 'ok', 'data': entry})

    # Return a stub for new strings so the user can save them
    return JsonResponse({
        'status': 'ok',
        'data': {
            'msgid': msgid,
            'ru': msgid, # default to msgid for RU
            'en': '',
            'pl': '',
            'is_new': True,
            'source_ru': 'po',
            'source_en': 'po',
            'source_pl': 'po'
        }
    })


@user_passes_test(can_use_translation_studio)
def scan_translations_api(request: HttpRequest) -> JsonResponse:
    """Return a mapping of translated text -> msgid for the current language."""
    lang = getattr(request, 'LANGUAGE_CODE', None)
    if not lang:
        from django.utils import translation as _t
        lang = _t.get_language() or 'en'

    translations = load_all_translations()
    mapping = {}
    import re

    def normalize(s: Any) -> str:
        if not s:
            return ""
        return re.sub(r'\s+', ' ', str(s)).strip()

    for entry in translations:
        msgid = entry['msgid']
        mapping[normalize(msgid)] = msgid

        for lang_code in ['ru', 'en', 'pl']:
            val = entry.get(lang_code)
            if val:
                mapping[normalize(val)] = msgid

    return JsonResponse({'status': 'ok', 'data': mapping})
