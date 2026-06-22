from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

from django.db import models
from django.utils import timezone

from clients.models import ClientActivity

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
    from django.http import HttpRequest

    from clients.models import Case, Client, Document, Payment, StaffTask


DANGEROUS_ACTIVITY_METADATA_KEYS = {
    "email",
    "first_name",
    "last_name",
    "full_name",
    "phone",
    "employer_phone",
    "passport",
    "passport_num",
    "passport_number",
    "pesel",
    "birth_date",
    "address",
    "full_address",
    "token",
    "token_hash",
    "text",
    "raw_text",
    "ocr_text",
    "content",
    "body",
    "notes",
    "comment",
    "total_amount",
    "amount_due",
    "amount_paid",
    "transaction_id",
    "rejection_reason",
    "case_number",
    "internal_number",
    "authority_case_number",
}


def _metadata_key_is_sensitive(key: Any, value: Any) -> bool:
    normalized = str(key).lower()
    if normalized in DANGEROUS_ACTIVITY_METADATA_KEYS:
        return True
    if normalized.endswith("_case_number") and normalized != "has_case_number":
        return not isinstance(value, bool)
    return False


def _sanitize_metadata_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, child_value in value.items():
            if _metadata_key_is_sensitive(key, child_value):
                continue
            sanitized[str(key)] = _sanitize_metadata_value(child_value)
        return sanitized
    if isinstance(value, list | tuple):
        return [_sanitize_metadata_value(item) for item in value]
    return value


def sanitize_activity_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    sanitized: dict[str, Any] = {}
    for key, value in metadata.items():
        if _metadata_key_is_sensitive(key, value):
            continue
        sanitized[str(key)] = _sanitize_metadata_value(value)
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
