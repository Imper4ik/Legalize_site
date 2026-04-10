import json
import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .utils import load_all_translations, save_translation_entry

logger = logging.getLogger(__name__)

# Admin-only views
is_superuser = lambda u: u.is_authenticated and u.is_superuser

@user_passes_test(is_superuser)
def studio_dashboard(request):
    """Render the side-by-side translation dashboard."""
    translations = load_all_translations()
    return render(request, 'translations/studio_dashboard.html', {
        'translations': translations,
        'languages': ['ru', 'en', 'pl']
    })

@csrf_exempt
@user_passes_test(is_superuser)
def update_translation_api(request):
    """API to save a single translation msgid across all languages."""
    if request.method == 'POST':
        try:
            # Defensive decode of request body for logging
            body = request.body.decode('utf-8') if isinstance(request.body, (bytes, bytearray)) else str(request.body)
            try:
                data = json.loads(body)
            except Exception:
                data = {}

            msgid = data.get('msgid')
            # Fetch languages
            ru = data.get('ru')
            en = data.get('en')
            pl = data.get('pl')

            logger.info('update_translation_api called by %s referer=%s payload=%s', getattr(request, 'user', None), request.META.get('HTTP_REFERER'), data)

            save_translation_entry(msgid, ru=ru, en=en, pl=pl)
            logger.info('Saved translation for msgid=%s', msgid)
            return JsonResponse({'status': 'ok'})
        except Exception as e:
            logger.exception('Error in update_translation_api: %s', e)
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

@user_passes_test(is_superuser)
def toggle_studio_mode(request):
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
    return redirect(request.META.get('HTTP_REFERER', '/'))

@user_passes_test(is_superuser)
def get_translation_api(request):
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
            'is_new': True
        }
    })


@user_passes_test(is_superuser)
def scan_translations_api(request):
    """Return a mapping of translated text -> msgid for the current language.

    This is used by the in-context editor to find translation occurrences that
    were not wrapped server-side (e.g. dynamically included partials).
    """
    lang = getattr(request, 'LANGUAGE_CODE', None)
    if not lang:
        from django.utils import translation as _t
        lang = _t.get_language() or 'en'

    translations = load_all_translations()
    mapping = {}
    import re
    def normalize(s):
        if not s: return ""
        return re.sub(r'\s+', ' ', str(s)).strip()

    for entry in translations:
        msgid = entry['msgid']
        # Map the msgid itself
        mapping[normalize(msgid)] = msgid
        
        # Map ALL localized versions
        for lang_code in ['ru', 'en', 'pl']:
            val = entry.get(lang_code)
            if val:
                mapping[normalize(val)] = msgid

    return JsonResponse({'status': 'ok', 'data': mapping})
