from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

from django.db import models
from django.utils import timezone

from clients.models import ClientActivity

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
    from django.http import HttpRequest

    from clients.models import Client, Document, Payment, StaffTask


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
) -> ClientActivity:
    # AnonymousUser cannot be assigned to ForeignKey
    real_actor = actor if actor and actor.is_authenticated else None

    return ClientActivity.objects.create(
        client=client,
        actor=cast(Any, real_actor),
        event_type=event_type,
        summary=summary,
        details=details,
        metadata=metadata or {},
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
