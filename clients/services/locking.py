from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.db.models import F
from django.utils import timezone

from clients.models import (
    Case,
    ClientDocumentRequirement,
    Document,
    MOSApplicationData,
    Payment,
    PeselApplication,
    Reminder,
    StaffTask,
    WniosekSubmission,
)
from clients.services.access import is_internal_staff_user
from clients.services.roles import user_has_any_role

logger = logging.getLogger(__name__)


def has_edit_permission(actor: Any) -> bool:
    if actor is None or not getattr(actor, "is_authenticated", False):
        return False
    if getattr(actor, "is_superuser", False):
        return True
    if user_has_any_role(actor, "ReadOnly"):
        return False
    if user_has_any_role(actor, "Admin", "Manager", "Staff"):
        return True
    return is_internal_staff_user(actor)


def _update_instance_with_locking(
    model_class: type[models.Model],
    instance_id: int,
    expected_version: int,
    actor: Any,
    changes_dict: dict[str, Any],
    whitelist: set[str],
    version_field_name: str = "version",
    event_type: str = "field_updated",
) -> Any:
    if not has_edit_permission(actor):
        raise PermissionDenied("У вас нет прав для редактирования этой записи.")

    instance = model_class._base_manager.get(pk=instance_id)

    # Проверяем согласованность client и case
    if hasattr(instance, "client_id") and hasattr(instance, "case_id"):
        case_id = changes_dict.get("case_id", getattr(instance, "case_id"))
        client_id = changes_dict.get("client_id", getattr(instance, "client_id"))
        if case_id and client_id:
            if getattr(instance, "case").client_id != client_id:
                raise ValidationError("Клиент и дело не согласованы.")

    prepared_changes: dict[str, Any] = {}
    for key, value in changes_dict.items():
        if key not in whitelist:
            continue
        prepared_changes[key] = value

    for key, value in prepared_changes.items():
        setattr(instance, key, value)

    instance.full_clean()

    filter_kwargs = {
        "pk": instance_id,
        version_field_name: expected_version,
    }

    update_kwargs: dict[str, Any] = {
        version_field_name: F(version_field_name) + 1,
    }

    if hasattr(instance, "updated_at"):
        update_kwargs["updated_at"] = timezone.now()

    for key, value in prepared_changes.items():
        field = model_class._meta.get_field(key)
        if isinstance(field, models.ForeignKey):
            if isinstance(value, models.Model):
                update_kwargs[field.attname] = value.pk
            else:
                update_kwargs[field.attname] = value
        else:
            update_kwargs[key] = value

    # This bulk .update() bypasses Model.save(), so derived columns normally
    # recomputed there are not refreshed. Case.authority_case_number_hash backs
    # the navbar "wezwanie без номера дела" filter, so without this the number
    # would be stored but the hash (and the alert) would stay stale forever.
    if model_class is Case and "authority_case_number" in prepared_changes:
        number = prepared_changes["authority_case_number"]
        update_kwargs["authority_case_number_hash"] = (
            Case.hash_case_number(number) if number else ""
        )

    updated = model_class._base_manager.filter(**filter_kwargs).update(**update_kwargs)
    if updated == 0:
        raise ValidationError("Данные были изменены другим сотрудником. Проверьте актуальную версию перед сохранением.")

    from clients.services.activity import log_client_activity
    client = getattr(instance, "client", None)
    case = getattr(instance, "case", None)
    if client:
        log_client_activity(
            client=client,
            case=case,
            actor=actor,
            event_type=event_type,
            summary="Запись обновлена",
            metadata={
                **({"case_id": str(case.uuid)} if case else {}),
                "status_tag": "approved" if getattr(instance, "status", "") == "approved" else "submitted",
            },
        )

    # The bulk .update() above bypasses post_save signals, so the navbar
    # attention cache is not invalidated automatically — refresh it here so the
    # edited record's counts (wezwanie/legal-stay/…) update immediately.
    if client is not None:
        from clients.services.onboarding_purposes import clear_onboarding_notifications_cache
        try:
            clear_onboarding_notifications_cache(client)
        except Exception:
            logger.warning("Failed to clear onboarding notifications cache after locked update")

    return model_class._base_manager.get(pk=instance_id)


CASE_WHITELIST = {
    "authority_case_number", "legacy_case_number", "needs_manual_number_check",
    "status", "workflow_stage",
    "application_purpose", "application_type", "basis_of_stay", "opened_at",
    "submission_date", "fingerprints_date", "fingerprints_time", "fingerprints_location",
    "fingerprints_ticket", "fingerprints_list", "fingerprints_info", "decision",
    "decision_date", "company"
}

PAYMENT_WHITELIST = {
    "service_description", "total_amount", "amount_paid", "status",
    "payment_method", "payment_date", "due_date"
}

REMINDER_WHITELIST = {
    "reminder_type", "title", "notes", "due_date", "is_active"
}

MOS_WHITELIST = {
    "status", "mos_purpose", "legal_stay_until", "personal_data",
    "passport_data", "address_data", "stay_data", "previous_stays",
    "travel_history", "insurance_data", "financial_data", "legal_declarations",
    "new_residence_card_application_status", "new_residence_card_case_number",
    "new_residence_card_submitted_at", "new_residence_card_comment"
}

PESEL_WHITELIST = {
    "status", "legal_basis", "pesel_form_data", "notes"
}

REQUIREMENT_WHITELIST = {
    "document_type", "name", "description", "is_required", "due_date", "is_active"
}

TASK_WHITELIST = {
    "title", "description", "status", "due_date", "assignee"
}

WNIOSEK_WHITELIST = {
    "document_kind", "attachment_count"
}

DOCUMENT_WHITELIST = {
    "document_type", "notes", "expiry_date", "rejection_reason"
}


def update_case_with_version(case_id: int, expected_version: int, actor: Any, changes_dict: dict[str, Any]) -> Case:
    return _update_instance_with_locking(Case, case_id, expected_version, actor, changes_dict, CASE_WHITELIST, event_type="case_updated")


def update_payment_with_version(payment_id: int, expected_version: int, actor: Any, changes_dict: dict[str, Any]) -> Payment:
    return _update_instance_with_locking(Payment, payment_id, expected_version, actor, changes_dict, PAYMENT_WHITELIST, event_type="payment_updated")


def update_reminder_with_version(reminder_id: int, expected_version: int, actor: Any, changes_dict: dict[str, Any]) -> Reminder:
    return _update_instance_with_locking(Reminder, reminder_id, expected_version, actor, changes_dict, REMINDER_WHITELIST, event_type="reminder_updated")


def update_mos_with_version(mos_id: int, expected_version: int, actor: Any, changes_dict: dict[str, Any]) -> MOSApplicationData:
    return _update_instance_with_locking(MOSApplicationData, mos_id, expected_version, actor, changes_dict, MOS_WHITELIST, event_type="mos_updated")


def update_pesel_with_version(pesel_id: int, expected_version: int, actor: Any, changes_dict: dict[str, Any]) -> PeselApplication:
    return _update_instance_with_locking(PeselApplication, pesel_id, expected_version, actor, changes_dict, PESEL_WHITELIST, event_type="pesel_updated")


def update_requirement_with_version(requirement_id: int, expected_version: int, actor: Any, changes_dict: dict[str, Any]) -> ClientDocumentRequirement:
    return _update_instance_with_locking(ClientDocumentRequirement, requirement_id, expected_version, actor, changes_dict, REQUIREMENT_WHITELIST, event_type="requirement_updated")


def update_staff_task_with_version(task_id: int, expected_version: int, actor: Any, changes_dict: dict[str, Any]) -> StaffTask:
    return _update_instance_with_locking(StaffTask, task_id, expected_version, actor, changes_dict, TASK_WHITELIST, event_type="task_updated")


def update_wniosek_submission_with_version(submission_id: int, expected_version: int, actor: Any, changes_dict: dict[str, Any]) -> WniosekSubmission:
    return _update_instance_with_locking(WniosekSubmission, submission_id, expected_version, actor, changes_dict, WNIOSEK_WHITELIST, event_type="wniosek_updated")


def update_document_with_version(document_id: int, expected_metadata_version: int, actor: Any, changes_dict: dict[str, Any]) -> Document:
    return _update_instance_with_locking(Document, document_id, expected_metadata_version, actor, changes_dict, DOCUMENT_WHITELIST, version_field_name="metadata_version", event_type="document_updated")
