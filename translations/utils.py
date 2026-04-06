import os
import logging
import polib
from django.conf import settings

import re
logger = logging.getLogger(__name__)

def normalize_text(s):
    """Normalize whitespace and newlines for comparison."""
    if not s: return ""
    return re.sub(r'\s+', ' ', str(s)).strip()

def get_po_files():
    """Returns a dict of language_code -> path to django.po"""
    locales_dir = os.path.join(settings.BASE_DIR, 'locale')
    langs = ['ru', 'en', 'pl']
    files = {}
    for lang in langs:
        path = os.path.join(locales_dir, lang, 'LC_MESSAGES', 'django.po')
        if os.path.exists(path):
            files[lang] = path
    return files

def load_all_translations():
    """
    Returns a unified list of translations.
    Format: [
        {'msgid': '...', 'ru': '...', 'en': '...', 'pl': '...', 'occurrences': [...]},
        ...
    ]
    """
    po_files = get_po_files()
    data = {}
    
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
                    'comment': entry.comment
                }
            data[entry.msgid][lang] = entry.msgstr
            
    # Convert to sorted list (by msgid)
    result = sorted(data.values(), key=lambda x: x['msgid'])
    return result

def save_translation_entry(msgid, ru=None, en=None, pl=None):
    """Updates a specific msgid in all 3 PO files."""
    po_files = get_po_files()
    updates = {'ru': ru, 'en': en, 'pl': pl}
    # Determine canonical msgid: if any PO already contains this string as
    # msgid or as a msgstr, prefer the existing msgid so we update the
    # canonical entry rather than creating duplicates.
    canonical = msgid
    normalized_input = normalize_text(msgid)
    
    # Track potential matches. 
    # We prefer: 1) Exact msgid, 2) Normalized msgid, 3) msgstr match
    potential_canonical = None

    try:
        for l, p in po_files.items():
            try:
                po = polib.pofile(p)
            except Exception:
                continue
            
            for entry in po:
                if not entry.msgid: continue
                
                n_id = normalize_text(entry.msgid)
                n_str = normalize_text(entry.msgstr)

                # 1. Exact msgid match (Strongest)
                if entry.msgid == msgid:
                    canonical = entry.msgid
                    logger.info('Found exact msgid match in %s: %s', l, canonical)
                    potential_canonical = canonical
                    break
                
                # 2. Normalized msgid match (Secondary)
                if not potential_canonical and n_id == normalized_input:
                    potential_canonical = entry.msgid
                    logger.info('Found normalized msgid match in %s: %s', l, potential_canonical)
                
                # 3. msgstr match (Resolution from UI text to technical key)
                if not potential_canonical and n_str == normalized_input:
                    potential_canonical = entry.msgid
                    logger.info('Found msgstr match (resolved UI text to key) in %s: %s', l, potential_canonical)
            
            if potential_canonical and potential_canonical == msgid: # Already found best possible
                break

    except Exception as e:
        logger.error('Error during canonical resolution: %s', e)

    if potential_canonical:
        canonical = potential_canonical

    # Now update each language PO under the canonical msgid
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
            old = entry.msgstr
            entry.msgstr = updates[lang]
            if 'fuzzy' in entry.flags:
                entry.flags.remove('fuzzy')
            try:
                po.save()
                logger.info('Updated translation in %s for msgid=%s (lang=%s): "%s" -> "%s"', path, canonical, lang, old, updates[lang])
            except Exception as e:
                logger.exception('Failed to save PO file %s: %s', path, e)
        else:
            # Create a new entry if it doesn't exist (use canonical msgid)
            new_entry = polib.POEntry(
                msgid=canonical,
                msgstr=updates[lang],
                comment="Dynamically added via Translation Studio"
            )
            po.append(new_entry)
            try:
                po.save()
                logger.info('Appended new translation to %s for msgid=%s (lang=%s): "%s"', path, canonical, lang, updates[lang])
            except Exception as e:
                logger.exception('Failed to save PO file %s after append: %s', path, e)
            
    # Optional: trigger compilemessages? 
    # Usually better to do it once at the end of multiple edits, 
    # but for in-context, live feedback is nice.
    from django.core.management import call_command
    call_command('compilemessages')
