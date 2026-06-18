from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from clients.models import Client

ONBOARDING_PURPOSE_CHOICES = (
    ("study", _("Учёба")),
    ("work", _("Работа")),
    ("family_spouse", _("Воссоединение с супругом")),
    ("family_child", _("Воссоединение с ребёнком")),
)
ALLOWED_ONBOARDING_PURPOSES = {value for value, _label in ONBOARDING_PURPOSE_CHOICES}
ONBOARDING_PURPOSE_LABELS = dict(ONBOARDING_PURPOSE_CHOICES)
FAMILY_ONBOARDING_PURPOSES = {"family_spouse", "family_child"}
FAMILY_REQUIREMENT_ROLES = FAMILY_ONBOARDING_PURPOSES | {"sponsor"}


def normalize_onboarding_purpose(value: str | None) -> str:
    selected = (value or "").strip()
    if selected not in ALLOWED_ONBOARDING_PURPOSES:
        raise ValueError("Invalid application purpose.")
    return selected


def purpose_label(purpose: str | None) -> str:
    if not purpose:
        return str(_("не выбрана"))
    return str(ONBOARDING_PURPOSE_LABELS.get(purpose, str(purpose)))


def onboarding_purpose_mismatch_q() -> Q:
    selected_allowed = Q(mos_application_data__mos_purpose__in=ALLOWED_ONBOARDING_PURPOSES)
    family_member_mismatch = (
        Q(application_purpose="family", family_role__in=FAMILY_ONBOARDING_PURPOSES)
        & ~Q(mos_application_data__mos_purpose=F("family_role"))
    )
    family_sponsor_mismatch = Q(application_purpose="family", family_role="sponsor") & ~Q(
        mos_application_data__mos_purpose="work"
    )
    family_unresolved_mismatch = Q(application_purpose="family") & ~Q(family_role__in=FAMILY_REQUIREMENT_ROLES)
    direct_purpose_mismatch = ~Q(application_purpose="family") & ~Q(
        mos_application_data__mos_purpose=F("application_purpose")
    )
    return selected_allowed & (
        family_member_mismatch
        | family_sponsor_mismatch
        | family_unresolved_mismatch
        | direct_purpose_mismatch
    )


def onboarding_purpose_requires_review(client: Client) -> bool:
    mos_data = getattr(client, "mos_application_data", None)
    selected = getattr(mos_data, "mos_purpose", "") if mos_data else ""
    return bool(selected in ALLOWED_ONBOARDING_PURPOSES and selected != client.get_document_requirement_purpose())


def attach_onboarding_purpose_review_state(client: Client) -> Client:
    mos_data = getattr(client, "mos_application_data", None)
    selected = getattr(mos_data, "mos_purpose", "") if mos_data else ""
    current = client.get_document_requirement_purpose()
    setattr(client, "onboarding_purpose_requires_review", onboarding_purpose_requires_review(client))
    setattr(client, "onboarding_selected_purpose", selected)
    setattr(client, "onboarding_selected_purpose_label", purpose_label(selected))
    setattr(client, "onboarding_card_purpose", current)
    setattr(client, "onboarding_card_purpose_label", purpose_label(current))
    return client


def apply_onboarding_purpose_to_client(client: Client, selected_purpose: str) -> list[str]:
    """Apply a document-requirement purpose to the staff-owned client card."""
    purpose = normalize_onboarding_purpose(selected_purpose)
    changed_fields: list[str] = []

    if purpose in FAMILY_ONBOARDING_PURPOSES:
        updates = {"application_purpose": "family", "family_role": purpose}
    else:
        updates = {"application_purpose": purpose, "family_role": ""}

    for field_name, value in updates.items():
        if getattr(client, field_name) != value:
            setattr(client, field_name, value)
            changed_fields.append(field_name)

    if changed_fields:
        client.save(update_fields=changed_fields)
    return changed_fields


def _notification_cache_languages() -> set[str]:
    languages = {str(getattr(settings, "LANGUAGE_CODE", "ru") or "ru")}
    languages.update({"ru", "pl", "en"})
    languages.update(str(code) for code, _label in getattr(settings, "LANGUAGES", ()))
    return languages


def clear_onboarding_notifications_cache(client: Client | None = None) -> None:
    from clients.services.roles import ADMIN_PANEL_ALLOWED_ROLES

    user_model = get_user_model()
    users = user_model.objects.filter(is_active=True, is_staff=True).filter(
        Q(is_superuser=True) | Q(groups__name__in=ADMIN_PANEL_ALLOWED_ROLES)
    )
    if client and client.assigned_staff_id:
        users = users | user_model.objects.filter(pk=client.assigned_staff_id)

    for user_id in users.values_list("pk", flat=True).distinct():
        for language in _notification_cache_languages():
            cache.delete(f"onboarding_notifications:v3:user:{user_id}:lang:{language}")
            cache.delete(f"onboarding_notifications:v4:user:{user_id}:lang:{language}")
