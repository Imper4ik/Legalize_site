from __future__ import annotations

from django.conf import settings


def feature_flags(_request):
    """Expose feature flags needed by templates."""

    return {
        "translation_tooling_enabled": getattr(settings, "ENABLE_TRANSLATION_TOOLING", False),
    }
