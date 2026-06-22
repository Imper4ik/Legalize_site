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

ALLOWED_METADATA_SCHEMA = {
    "case_id": "uuid",
    "document_count": "int",
    "archive_batch_uuid": "uuid",
    "status_tag": {
        "archived",
        "restored",
        "submitted",
        "approved",
        "rejected",
    },
    "status": "str",
    "has_case_number": "bool",
    "path": "str",
    "method": "str",
    "export_type": "str",
    "payment_count": "int",
    "document_id": "int",
    "document_version_id": "int",
    "version_number": "int",
    "restored_version_id": "int",
    "restored_version_number": "int",
    "workflow_stage": "str",
    "changed_fields": "list",
    "auto_updates": "dict",
    "source": "str",
    "restored_object": "str",
    "restored_object_id": "int",
    "payment_id": "int",
    "task_id": "int",
    "verified": "bool",
    "verified_count": "int",
    "document_type": "str",
    "selected_purpose": "str",
    "priority": "str",
    "assignee_id": "int",
    "due_date": "str",
    "attachment_id": "int",
    "attachment_name": "str",
    "submission_id": "int",
    "remaining_count": "int",
    "submission_deleted": "bool",
    "old_workflow_stage": "str",
    "field": "str",
    "old_value": "str",
    "new_value": "str",
    "old_status": "str",
    "new_status": "str",
    "reminder_id": "int",
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
                logger.warning("Metadata key '%s' rejected due to type mismatch (expected UUID)", key)
                
        elif expected_type == "int":
            if isinstance(value, int) and not isinstance(value, bool):
                sanitized[key] = value
            elif isinstance(value, str) and value.isdigit():
                sanitized[key] = int(value)
            else:
                logger.warning("Metadata key '%s' rejected due to type mismatch (expected int)", key)
                
        elif expected_type == "str":
            if isinstance(value, (str, int, float, bool, uuid.UUID)):
                val_str = str(value)
            elif hasattr(value, "isoformat"):
                val_str = value.isoformat()
            else:
                val_str = None
                
            if val_str is not None:
                if len(val_str) <= 100:
                    sanitized[key] = val_str
                else:
                    logger.warning("Metadata key '%s' rejected due to string length limit (max 100)", key)
            else:
                logger.warning("Metadata key '%s' rejected due to type mismatch (expected str)", key)
                
        elif isinstance(expected_type, set):
            if isinstance(value, str) and value in expected_type:
                sanitized[key] = value
            else:
                logger.warning("Metadata key '%s' rejected due to value mismatch (expected one of %s)", key, expected_type)

        elif expected_type == "bool":
            if isinstance(value, bool):
                sanitized[key] = value
            else:
                logger.warning("Metadata key '%s' rejected due to type mismatch (expected bool)", key)

        elif expected_type == "list":
            if isinstance(value, (list, tuple)):
                sanitized_list = []
                for item in value:
                    if isinstance(item, (int, float)) and not isinstance(item, bool):
                        sanitized_list.append(item)
                    elif isinstance(item, bool):
                        sanitized_list.append(item)
                    elif isinstance(item, str) and len(item) <= 100:
                        sanitized_list.append(item)
                    elif hasattr(item, "isoformat"):
                        sanitized_list.append(item.isoformat())
                    else:
                        logger.warning("Metadata list item rejected due to type/length constraint")
                sanitized[key] = sanitized_list
            else:
                logger.warning("Metadata key '%s' rejected due to type mismatch (expected list)", key)

        elif expected_type == "dict":
            if isinstance(value, dict):
                def sanitize_val(val: Any) -> Any:
                    if isinstance(val, dict):
                        return {str(k): sanitize_val(v) for k, v in val.items() if len(str(k)) <= 100}
                    elif isinstance(val, (list, tuple)):
                        return [sanitize_val(v) for v in val]
                    elif isinstance(val, (int, float)) and not isinstance(val, bool):
                        return val
                    elif isinstance(val, bool):
                        return val
                    elif isinstance(val, str) and len(val) <= 100:
                        return val
                    elif hasattr(val, "isoformat"):
                        return val.isoformat()
                    return None
                sanitized[key] = sanitize_val(value)
            else:
                logger.warning("Metadata key '%s' rejected due to type mismatch (expected dict)", key)
                
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
