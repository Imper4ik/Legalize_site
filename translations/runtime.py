from __future__ import annotations

import hashlib
import logging
from typing import Any

from django.core.cache import cache
from django.db.utils import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

def get_cache_key(msgid: str, language: str) -> str:
    """Generate a cache key for a translation override."""
    msgid_hash = hashlib.sha256(msgid.encode("utf-8")).hexdigest()[:16]
    return f"trans_override:{language}:{msgid_hash}"

def get_db_translation_override(msgid: str, language: str) -> str | None:
    """Fetch translation override from DB with caching."""
    from django.conf import settings

    if not getattr(settings, "TRANSLATION_DB_OVERRIDES_ENABLED", True):
        return None

    cache_key = get_cache_key(msgid, language)
    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return cached_val if cached_val != "__NONE__" else None

    from .models import TranslationOverride

    try:
        override = TranslationOverride.objects.filter(
            msgid=msgid, language=language, is_active=True
        ).first()
        if override:
            cache.set(cache_key, override.text, timeout=3600)  # Cache for 1 hour
            return override.text
        else:
            cache.set(cache_key, "__NONE__", timeout=3600)
            return None
    except (ProgrammingError, OperationalError):
        # Table might not exist yet or DB issue
        return None
    except Exception as e:
        logger.exception("Error fetching translation override: %s", e)
        return None

def apply_db_override(msgid: str, translated: str, language: str | None = None) -> str:
    """Apply DB override on top of a translated string."""
    if language is None:
        from django.utils import translation
        language = translation.get_language()

    if not language:
        return translated

    override = get_db_translation_override(msgid, language)
    if override is not None:
        return override
    return translated

def clear_translation_override_cache(msgid: str, language: str) -> None:
    """Clear cache for a specific translation override."""
    cache_key = get_cache_key(msgid, language)
    cache.delete(cache_key)
    logger.debug("Cleared translation cache for %s (%s)", msgid[:20], language)
