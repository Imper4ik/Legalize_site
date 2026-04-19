from __future__ import annotations

from datetime import timedelta

from django.db import models
from django.utils import timezone

from clients.models import ClientActivity


def log_client_activity(
    *,
    client,
    event_type: str,
    summary: str,
    actor=None,
    details: str = "",
    metadata: dict | None = None,
    document=None,
    payment=None,
    task=None,
):
    return ClientActivity.objects.create(
        client=client,
        actor=actor,
        event_type=event_type,
        summary=summary,
        details=details,
        metadata=metadata or {},
        document=document,
        payment=payment,
        task=task,
    )


def log_client_view(*, client, actor, request=None):
    if actor is None:
        return None

    recent_threshold = timezone.now() - timedelta(minutes=15)
    if ClientActivity.objects.filter(
        client=client,
        actor=actor,
        event_type="client_viewed",
        created_at__gte=recent_threshold,
    ).exists():
        return None

    metadata = {}
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
            labels.append(str(instance._meta.get_field(field_name).verbose_name))
        except Exception:
            labels.append(field_name.replace("_", " "))
    return labels
