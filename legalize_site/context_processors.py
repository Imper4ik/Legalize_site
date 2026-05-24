from __future__ import annotations

from typing import Any

from django.conf import settings
from django.http import HttpRequest
from django.urls import get_resolver


def feature_flags(request: HttpRequest) -> dict[str, Any]:
    """Expose feature flags needed by templates."""

    translation_tooling_enabled = getattr(settings, "ENABLE_TRANSLATION_TOOLING", False)
    translations_namespace_available = "translations" in get_resolver().namespace_dict

    return {
        "translation_tooling_enabled": translation_tooling_enabled,
        "translation_studio_available": translation_tooling_enabled and translations_namespace_available,
    }


def onboarding_notifications(request: HttpRequest) -> dict[str, Any]:
    if not request.user.is_authenticated:
        return {}
        
    from clients.services.access import is_internal_staff_user
    if not is_internal_staff_user(request.user):
        return {}
        
    from clients.models import Client
    from clients.services.access import accessible_clients_queryset
    
    try:
        qs = accessible_clients_queryset(request.user, Client.objects.all())
        count = qs.filter(mos_application_data__status="client_completed").count()
        return {
            "completed_onboarding_count": count
        }
    except Exception:
        return {}

