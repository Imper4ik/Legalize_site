from __future__ import annotations

from typing import Any

from django.conf import settings
from django.http import HttpRequest
from django.urls import get_resolver, reverse
from django.utils.translation import gettext as _


def feature_flags(request: HttpRequest) -> dict[str, Any]:
    """Expose feature flags needed by templates."""

    translation_tooling_enabled = getattr(settings, "ENABLE_TRANSLATION_TOOLING", False)
    translations_namespace_available = "translations" in get_resolver().namespace_dict

    return {
        "translation_tooling_enabled": translation_tooling_enabled,
        "translation_studio_available": translation_tooling_enabled and translations_namespace_available,
    }


def onboarding_notifications(request: HttpRequest) -> dict[str, Any]:
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {}

    from clients.services.access import is_internal_staff_user
    if not is_internal_staff_user(request.user):
        return {}

    from django.db.models import Q
    from clients.models import Client
    from clients.services.access import accessible_clients_queryset

    try:
        qs = accessible_clients_queryset(
            request.user,
            Client.objects.filter(Q(user__is_staff=False) | Q(user__isnull=True)),
        )
        completed_onboarding_count = qs.filter(mos_application_data__status="client_completed").count()
        ocr_review_count = qs.filter(
            documents__awaiting_confirmation=True,
            documents__archived_at__isnull=True,
        ).distinct().count()
        ocr_warning_count = qs.filter(
            documents__ocr_name_mismatch=True,
            documents__archived_at__isnull=True,
        ).distinct().count()
        ocr_pending_count = qs.filter(
            documents__ocr_status="pending",
            documents__archived_at__isnull=True,
        ).distinct().count()

        client_list_url = reverse("clients:client_list")
        items = []
        if completed_onboarding_count:
            items.append({
                "label": _("Заполненные анкеты"),
                "count": completed_onboarding_count,
                "url": f"{client_list_url}?onboarding=completed",
                "icon": "bi-file-earmark-check",
                "level": "success",
            })
        if ocr_review_count:
            items.append({
                "label": _("OCR требует подтверждения"),
                "count": ocr_review_count,
                "url": f"{client_list_url}?document=ocr_review",
                "icon": "bi-eye",
                "level": "warning",
            })
        if ocr_warning_count:
            items.append({
                "label": _("OCR предупреждения"),
                "count": ocr_warning_count,
                "url": f"{client_list_url}?document=ocr_warning",
                "icon": "bi-exclamation-triangle",
                "level": "danger",
            })
        if ocr_pending_count:
            items.append({
                "label": _("OCR обрабатывается"),
                "count": ocr_pending_count,
                "url": f"{client_list_url}?document=ocr_pending",
                "icon": "bi-hourglass-split",
                "level": "info",
            })

        return {
            "completed_onboarding_count": completed_onboarding_count,
            "client_attention_count": sum(item["count"] for item in items),
            "client_attention_items": items,
        }
    except Exception:
        return {}

def onboarding_progress(request: HttpRequest) -> dict[str, Any]:
    resolver_match = getattr(request, "resolver_match", None)
    if not resolver_match:
        return {}
    
    url_name = resolver_match.url_name
    steps = {
        "onboarding_digital_access": 1,
        "onboarding_passport": 2,
        "onboarding_personal_extra": 3,
        "onboarding_address": 4,
        "onboarding_travel": 5,
        "onboarding_declarations": 6,
        "onboarding_review": 7,
    }
    
    if url_name in steps:
        step_num = steps[url_name]
        total_steps = 7
        percent = int((step_num / total_steps) * 100)
        return {
            "onboarding_step_num": step_num,
            "onboarding_step_total": total_steps,
            "onboarding_step_percent": percent,
        }
    return {}


