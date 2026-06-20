from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest
from django.urls import get_resolver, reverse
from django.utils import translation
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

    from clients.models import Client, StaffTask
    from clients.services.access import accessible_clients_queryset, accessible_tasks_queryset
    from clients.services.attention import count_client_attention_filters
    from clients.services.onboarding_purposes import onboarding_purpose_mismatch_q

    language = translation.get_language() or getattr(settings, "LANGUAGE_CODE", "")
    cache_key = f"onboarding_notifications:v5:user:{request.user.pk}:lang:{language}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        qs = accessible_clients_queryset(
            request.user,
            Client.objects.filter(Q(user__is_staff=False) | Q(user__isnull=True)),
        )
        completed_onboarding_count = qs.filter(mos_application_data__status="client_completed").count()
        purpose_change_count = qs.filter(onboarding_purpose_mismatch_q()).count()
        staff_review_count = qs.filter(mos_application_data__status="staff_review").count()
        submitted_in_mos_count = qs.filter(mos_application_data__status="submitted_in_mos").count()
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

        ocr_failed_count = qs.filter(
            documents__ocr_status="failed",
            documents__archived_at__isnull=True,
        ).distinct().count()
        attention_counts = count_client_attention_filters(qs)
        pending_question_tasks = accessible_tasks_queryset(
            request.user,
            StaffTask.objects.filter(
                status__in=["open", "in_progress"],
                description__startswith="Клиент задал вопрос через приложение:",
            ),
        ).select_related("client").order_by("-created_at")
        pending_question_count = pending_question_tasks.count()
        pending_question_preview = list(pending_question_tasks[:5])

        client_list_url = reverse("clients:client_list")
        items = []
        if pending_question_count:
            items.append({
                "label": _("Вопросы клиентов"),
                "count": pending_question_count,
                "url": f"{reverse('clients:task_list')}?type=questions",
                "icon": "bi-envelope-paper",
                "level": "danger",
            })
        if attention_counts["legal_stay"]:
            items.append({
                "label": _("Истекает легальное пребывание"),
                "count": attention_counts["legal_stay"],
                "url": f"{client_list_url}?attention=legal_stay",
                "icon": "bi-calendar-x",
                "level": "danger",
            })
        if attention_counts["expired_documents"]:
            items.append({
                "label": _("Просроченные документы"),
                "count": attention_counts["expired_documents"],
                "url": f"{client_list_url}?attention=expired_documents",
                "icon": "bi-file-earmark-x",
                "level": "danger",
            })
        if attention_counts["expiring_documents"]:
            items.append({
                "label": _("Документы скоро истекают"),
                "count": attention_counts["expiring_documents"],
                "url": f"{client_list_url}?attention=expiring_documents",
                "icon": "bi-file-earmark-medical",
                "level": "warning",
            })
        if attention_counts["unverified_documents"]:
            items.append({
                "label": _("Документы ждут проверки"),
                "count": attention_counts["unverified_documents"],
                "url": f"{client_list_url}?attention=unverified_documents",
                "icon": "bi-file-earmark-check",
                "level": "warning",
            })
        if attention_counts["overdue_payments"]:
            items.append({
                "label": _("Просроченные оплаты"),
                "count": attention_counts["overdue_payments"],
                "url": f"{client_list_url}?attention=overdue_payments",
                "icon": "bi-credit-card-2-back",
                "level": "warning",
            })
        if attention_counts["failed_emails"]:
            items.append({
                "label": _("Ошибки отправки email"),
                "count": attention_counts["failed_emails"],
                "url": f"{client_list_url}?attention=failed_emails",
                "icon": "bi-envelope-exclamation",
                "level": "danger",
            })
        if attention_counts["fingerprints_email"]:
            items.append({
                "label": _("Письмо по отпечаткам не отправлено"),
                "count": attention_counts["fingerprints_email"],
                "url": f"{client_list_url}?attention=fingerprints_email",
                "icon": "bi-fingerprint",
                "level": "warning",
            })
        if attention_counts["overdue_tasks"]:
            items.append({
                "label": _("Просроченные задачи"),
                "count": attention_counts["overdue_tasks"],
                "url": f"{client_list_url}?attention=overdue_tasks",
                "icon": "bi-list-task",
                "level": "danger",
            })
        if attention_counts["wezwanie_missing_case"]:
            items.append({
                "label": _("Wezwanie без номера дела"),
                "count": attention_counts["wezwanie_missing_case"],
                "url": f"{client_list_url}?attention=wezwanie_missing_case",
                "icon": "bi-journal-text",
                "level": "warning",
            })
        if attention_counts["new_card_missing_case"]:
            items.append({
                "label": _("Новая подача без основного номера"),
                "count": attention_counts["new_card_missing_case"],
                "url": f"{client_list_url}?attention=new_card_missing_case",
                "icon": "bi-file-earmark-plus",
                "level": "warning",
            })
        if purpose_change_count:
            items.append({
                "label": _("Смена основания"),
                "count": purpose_change_count,
                "url": f"{client_list_url}?onboarding=purpose_change",
                "icon": "bi-exclamation-diamond",
                "level": "warning",
            })
        if completed_onboarding_count:
            items.append({
                "label": _("Client completed"),
                "count": completed_onboarding_count,
                "url": f"{client_list_url}?onboarding=completed",
                "icon": "bi-file-earmark-check",
                "level": "success",
            })
        if staff_review_count:
            items.append({
                "label": _("Staff review"),
                "count": staff_review_count,
                "url": f"{client_list_url}?onboarding=staff_review",
                "icon": "bi-clock",
                "level": "warning",
            })
        if submitted_in_mos_count:
            items.append({
                "label": _("Submitted in MOS"),
                "count": submitted_in_mos_count,
                "url": f"{client_list_url}?onboarding=submitted_in_mos",
                "icon": "bi-send",
                "level": "info",
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

        if ocr_failed_count:
            items.append({
                "label": _("OCR с ошибкой"),
                "count": ocr_failed_count,
                "url": f"{client_list_url}?document=ocr_failed",
                "icon": "bi-exclamation-octagon",
                "level": "danger",
            })

        context = {
            "completed_onboarding_count": completed_onboarding_count,
            "purpose_change_count": purpose_change_count,
            "attention_counts": attention_counts,
            "client_attention_count": sum(item["count"] for item in items),
            "client_attention_items": items,
            "pending_question_count": pending_question_count,
            "pending_question_tasks": pending_question_preview,
            "pending_question_url": f"{reverse('clients:task_list')}?type=questions",
        }
        cache.set(cache_key, context, int(getattr(settings, "ONBOARDING_NOTIFICATIONS_CACHE_SECONDS", 45)))
        return context
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


