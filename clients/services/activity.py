from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

from django.db import models
from django.utils import timezone

from clients.models import ClientActivity

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
    from django.http import HttpRequest

    from clients.models import Case, Client, Document, Payment, StaffTask


logger = logging.getLogger(__name__)

SAFE_FIELD_NAMES = {
    "status", "workflow_stage", "application_purpose", "application_type", "basis_of_stay",
    "opened_at", "submission_date", "fingerprints_date", "fingerprints_time", "fingerprints_location",
    "decision_date", "decision_valid_until", "assigned_staff", "company", "is_test_data", "is_demo_data",
    "due_date", "is_active", "notes", "description", "title", "document_type", "expiry_date",
    "total_amount", "amount_paid", "payment_method", "payment_date", "rejection_reason",
    "document_kind", "attachment_count", "metadata_version", "ocr_version", "version",
    "transaction_id"
}

ALLOWED_METADATA_SCHEMA = {
    "case_id": "uuid",
    "document_id": "uuid_or_int",
    "payment_id": "uuid_or_int",
    "task_id": "uuid_or_int",
    "reminder_id": "uuid_or_int",
    "archive_batch_uuid": "uuid",
    "document_count": "int",
    "payment_count": "int",
    "task_count": "int",
    "status_tag": {
        "archived",
        "restored",
        "submitted",
        "approved",
        "rejected",
    },
    "changed_fields": "safe_field_names_list",
    "restored_object": {
        "client",
        "document",
        "payment",
    },
    "restored_object_id": "uuid_or_int",
    "priority": "string",
    "document_type": "string",
    "export_type": "string",
    "attachment_id": "uuid_or_int",
    "restored_version_id": "uuid_or_int",
    "restored_version_number": "int",
    "verified_count": "int",
    "remaining_count": "int",
}


def sanitize_activity_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    sanitized: dict[str, Any] = {}
    for key, value in metadata.items():
        if key not in ALLOWED_METADATA_SCHEMA:
            logger.warning("Metadata key rejected due to security policy whitelist violation: %s", key)
            continue

        expected_type = ALLOWED_METADATA_SCHEMA[key]

        if expected_type == "uuid":
            if isinstance(value, uuid.UUID):
                sanitized[key] = str(value)
            elif isinstance(value, str):
                try:
                    parsed = uuid.UUID(value)
                    sanitized[key] = str(parsed)
                except ValueError:
                    logger.warning("Metadata key '%s' rejected due to invalid UUID format", key)
            else:
                logger.warning("Metadata key '%s' rejected due to type mismatch", key)

        elif expected_type == "uuid_or_int":
            if isinstance(value, int) and not isinstance(value, bool):
                sanitized[key] = value
            elif isinstance(value, uuid.UUID):
                sanitized[key] = str(value)
            elif isinstance(value, str):
                if value.isdigit():
                    sanitized[key] = int(value)
                else:
                    try:
                        parsed = uuid.UUID(value)
                        sanitized[key] = str(parsed)
                    except ValueError:
                        logger.warning("Metadata key '%s' rejected due to invalid UUID/int format", key)
            else:
                logger.warning("Metadata key '%s' rejected due to type mismatch", key)

        elif expected_type == "int":
            if isinstance(value, int) and not isinstance(value, bool):
                sanitized[key] = value
            elif isinstance(value, str) and value.isdigit():
                sanitized[key] = int(value)
            else:
                logger.warning("Metadata key '%s' rejected due to type mismatch", key)

        elif expected_type == "string":
            if isinstance(value, str):
                if len(value) <= 100:
                    sanitized[key] = value
                else:
                    logger.warning("Metadata key '%s' rejected due to string length limit", key)
            else:
                logger.warning("Metadata key '%s' rejected due to type mismatch", key)

        elif isinstance(expected_type, set):
            if isinstance(value, str) and value in expected_type:
                if len(value) <= 100:
                    sanitized[key] = value
                else:
                    logger.warning("Metadata key '%s' rejected due to string length limit", key)
            else:
                logger.warning("Metadata key '%s' rejected due to value mismatch", key)

        elif expected_type == "safe_field_names_list":
            if isinstance(value, (list, tuple)):
                sanitized_list = []
                for item in value:
                    if isinstance(item, str) and item in SAFE_FIELD_NAMES:
                        if len(item) <= 100:
                            sanitized_list.append(item)
                        else:
                            logger.warning("Metadata list item rejected due to string length limit")
                    else:
                        logger.warning("Metadata list item rejected because it is not a safe field name")
                sanitized[key] = sanitized_list
            else:
                logger.warning("Metadata key '%s' rejected due to type mismatch", key)

    return sanitized

    return sanitized


def log_client_activity(
    *,
    client: Client,
    event_type: str,
    summary: str,
    actor: AbstractBaseUser | AnonymousUser | None = None,
    details: str = "",
    metadata: dict[str, Any] | None = None,
    document: Document | None = None,
    payment: Payment | None = None,
    task: StaffTask | None = None,
    case: Case | None = None,
) -> ClientActivity:
    # AnonymousUser cannot be assigned to ForeignKey
    real_actor = actor if actor and actor.is_authenticated else None

    resolved_case = case
    if resolved_case is None:
        for source in (document, payment, task):
            source_case = getattr(source, "case", None) if source is not None else None
            if source_case is not None:
                resolved_case = source_case
                break

    return ClientActivity.objects.create(
        client=client,
        case=resolved_case,
        actor=cast(Any, real_actor),
        event_type=event_type,
        summary=summary,
        details=details,
        metadata=sanitize_activity_metadata(metadata),
        document=document,
        payment=payment,
        task=task,
    )

def log_client_view(*, client: Client, actor: AbstractBaseUser | AnonymousUser | None, request: HttpRequest | None = None) -> ClientActivity | None:
    if actor is None or not actor.is_authenticated:
        return None

    recent_threshold = timezone.now() - timedelta(minutes=15)
    if ClientActivity.objects.filter(
        client=client,
        actor=cast(Any, actor),
        event_type="client_viewed",
        created_at__gte=recent_threshold,
    ).exists():
        return None

    metadata: dict[str, Any] = {}
    if request is not None:
        metadata["path"] = request.path
        metadata["method"] = request.method

    return log_client_activity(
        client=client,
        actor=actor,
        event_type="client_viewed",
        summary="Карточка клиента открыта",
        metadata=metadata,
    )


def changed_field_labels(instance: models.Model, field_names: list[str]) -> list[str]:
    labels = []
    for field_name in field_names:
        try:
            field = instance._meta.get_field(field_name)
            if hasattr(field, "verbose_name"):
                labels.append(str(field.verbose_name))
            else:
                labels.append(field_name.replace("_", " "))
        except Exception:
            labels.append(field_name.replace("_", " "))
    return labels
