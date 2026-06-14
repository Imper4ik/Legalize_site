from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Any, Dict, List, Optional

import polib
from django.conf import settings

logger = logging.getLogger(__name__)


def _msgid_hash(msgid: Any) -> str:
    return hashlib.sha256(str(msgid or '').encode('utf-8')).hexdigest()[:12]


def normalize_text(s: Any) -> str:
    """Normalize whitespace and newlines for comparison."""
    if not s:
        return ""
    return re.sub(r'\s+', ' ', str(s)).strip()

def get_po_files() -> Dict[str, str]:
    """Returns a dict of language_code -> path to django.po"""
    locales_dir = os.path.join(str(settings.BASE_DIR), 'locale')
    langs = ['ru', 'en', 'pl']
    files = {}
    for lang in langs:
        path = os.path.join(locales_dir, lang, 'LC_MESSAGES', 'django.po')
        if os.path.exists(path):
            files[lang] = path
    return files

def load_all_translations() -> List[Dict[str, Any]]:
    """
    Returns a unified list of translations.
    Format: [
        {
            'msgid': '...',
            'ru': '...', 'en': '...', 'pl': '...',
            'occurrences': [...],
            'source_ru': 'po', 'source_en': 'po', 'source_pl': 'po'
        },
        ...
    ]
    """
    po_files = get_po_files()
    data: Dict[str, Dict[str, Any]] = {}

    # 1. Load from PO files
    for lang, path in po_files.items():
        po = polib.pofile(path)
        for entry in po:
            if not entry.msgid:
                continue
            if entry.msgid not in data:
                data[entry.msgid] = {
                    'msgid': entry.msgid,
                    'ru': '',
                    'en': '',
                    'pl': '',
                    'occurrences': entry.occurrences,
                    'comment': entry.comment,
                    'source_ru': 'po',
                    'source_en': 'po',
                    'source_pl': 'po'
                }
            data[entry.msgid][lang] = entry.msgstr
            data[entry.msgid][f'source_{lang}'] = 'po'

    # 2. Overlay DB overrides
    from django.db.utils import OperationalError, ProgrammingError

    from .models import TranslationOverride

    try:
        overrides = TranslationOverride.objects.filter(is_active=True)
        for override in overrides:
            if override.msgid not in data:
                data[override.msgid] = {
                    'msgid': override.msgid,
                    'ru': '',
                    'en': '',
                    'pl': '',
                    'occurrences': [],
                    'comment': 'Dynamically added via DB Override',
                    'source_ru': 'po',
                    'source_en': 'po',
                    'source_pl': 'po'
                }
            data[override.msgid][override.language] = override.text
            data[override.msgid][f'source_{override.language}'] = 'db'
    except (ProgrammingError, OperationalError):
        # Table might not exist yet or DB issue
        logger.debug("TranslationOverride table not found or DB error, skipping DB overrides.")

    # Convert to sorted list (by msgid)
    result = sorted(data.values(), key=lambda x: str(x['msgid']))
    return result

def save_translation_entry(
    msgid: str,
    ru: Optional[str] = None,
    en: Optional[str] = None,
    pl: Optional[str] = None,
    updated_by: Any = None,
    storage: Optional[str] = None,
) -> None:
    """Updates a specific msgid in PO files and/or DB."""
    if storage is None:
        storage = getattr(settings, 'TRANSLATION_STUDIO_STORAGE', 'database')

    po_files = get_po_files()
    updates = {'ru': ru, 'en': en, 'pl': pl}

    # Determine canonical msgid (keep existing logic for PO files)
    canonical = msgid
    normalized_input = normalize_text(msgid)
    potential_canonical: Optional[str] = None

    try:
        for language, path in po_files.items():
            try:
                po = polib.pofile(path)
            except Exception as exc:
                logger.debug('Skipping unreadable PO file %s: %s', path, exc)
                continue

            for entry in po:
                if not entry.msgid:
                    continue

                n_id = normalize_text(entry.msgid)
                n_str = normalize_text(entry.msgstr)

                if entry.msgid == msgid:
                    canonical = entry.msgid
                    potential_canonical = canonical
                    break

                if not potential_canonical and n_id == normalized_input:
                    potential_canonical = entry.msgid

                if not potential_canonical and n_str == normalized_input:
                    potential_canonical = entry.msgid

            if potential_canonical and potential_canonical == msgid:
                break
    except Exception as e:
        logger.error('Error during canonical resolution: %s', e)

    if potential_canonical:
        canonical = potential_canonical

    msgid_hash = _msgid_hash(canonical)

    # 1. Save to DB
    if storage in ('database', 'both'):
        from django.db.utils import OperationalError, ProgrammingError

        from .models import TranslationOverride
        from .runtime import clear_translation_override_cache

        for lang, value in updates.items():
            if value is None:
                continue

            try:
                _override, _created = TranslationOverride.objects.update_or_create(
                    msgid=canonical,
                    language=lang,
                    defaults={
                        'text': value,
                        'is_active': True,
                        'source': TranslationOverride.SOURCE_STUDIO,
                        'updated_by': updated_by if updated_by and updated_by.is_authenticated else None
                    }
                )
                logger.info('Saved DB translation override msgid_hash=%s lang=%s', msgid_hash, lang)
                # Clear cache
                clear_translation_override_cache(canonical, lang)
            except (ProgrammingError, OperationalError) as e:
                logger.warning('Failed to save to DB (table might not exist): %s', e)

    # 2. Save to PO files
    if storage in ('po', 'both'):
        for lang, path in po_files.items():
            if updates.get(lang) is None:
                continue

            try:
                po = polib.pofile(path)
            except Exception as e:
                logger.exception('Could not open PO file %s: %s', path, e)
                continue

            entry = po.find(canonical)

            if entry:
                entry.msgstr = updates[lang]
                if 'fuzzy' in entry.flags:
                    entry.flags.remove('fuzzy')
                try:
                    po.save()
                    logger.info('Updated translation in %s msgid_hash=%s lang=%s', path, msgid_hash, lang)
                except Exception as e:
                    logger.exception('Failed to save PO file %s: %s', path, e)
            else:
                new_entry = polib.POEntry(
                    msgid=canonical,
                    msgstr=updates[lang],
                    comment="Dynamically added via Translation Studio"
                )
                po.append(new_entry)
                try:
                    po.save()
                    logger.info('Appended new translation to %s msgid_hash=%s lang=%s', path, msgid_hash, lang)
                except Exception as e:
                    logger.exception('Failed to save PO file %s after append: %s', path, e)

        # Rebuild MO catalogs
        try:
            from legalize_site.utils.i18n import compile_message_catalogs
            compile_message_catalogs()
        except Exception as exc:
            logger.exception("Failed to compile translation catalogs after save: %s", exc)
