from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from clients.models import Case, CaseArchiveBatch, Client, ClientArchiveBatch, StaffTask
from clients.services.access import is_internal_staff_user
from clients.services.roles import user_has_any_role

logger = logging.getLogger(__name__)


def has_archive_permission(actor: Any) -> bool:
    if actor is None or not getattr(actor, "is_authenticated", False):
        return False
    if getattr(actor, "is_superuser", False):
        return True
    if user_has_any_role(actor, "ReadOnly"):
        return False
    if user_has_any_role(actor, "Admin", "Manager", "Staff"):
        return True
    return is_internal_staff_user(actor)


@transaction.atomic
def archive_case(
    case: Case,
    actor: Any,
    client_batch: ClientArchiveBatch | None = None,
) -> CaseArchiveBatch:
    if not has_archive_permission(actor):
        raise PermissionDenied("У вас нет прав для архивации дел.")

    case = Case.all_objects.select_for_update().get(pk=case.pk)

    if case.archived_at is not None:
        raise ValidationError("Дело уже заархивировано.")

    if CaseArchiveBatch.objects.filter(case=case, status="archived").exists():
        raise ValidationError("Активная архивация для этого дела уже существует.")

    if case.client.archived_at is not None and client_batch is None:
        raise ValidationError("Нельзя индивидуально архивировать дело, если клиент уже заархивирован.")

    case.archived_at = timezone.now()
    case.archived_by = actor
    case.save(update_fields=["archived_at", "archived_by"])

    batch = CaseArchiveBatch.objects.create(
        case=case,
        client_archive_batch=client_batch,
        archived_by=actor,
        status="archived",
    )

    tasks_count = StaffTask.objects.filter(
        case=case,
        status__in=["open", "in_progress"],
        suspended_by_case_archive=False
    ).update(
        suspended_by_case_archive=True,
        suspended_at=timezone.now(),
        suspended_by_archive_batch=batch
    )

    from clients.services.activity import log_client_activity
    log_client_activity(
        client=case.client,
        case=case,
        actor=actor,
        event_type="case_archived",
        summary="Дело заархивировано",
        metadata={
            "case_id": str(case.uuid),
            "archive_batch_uuid": str(batch.uuid),
            "status_tag": "archived",
            "task_count": tasks_count,
        }
    )

    return batch


@transaction.atomic
def restore_case(
    case: Case,
    actor: Any,
    batch: CaseArchiveBatch,
    allow_when_client_archived: bool = False,
) -> Case:
    if not has_archive_permission(actor):
        raise PermissionDenied("У вас нет прав для восстановления дел.")

    case = Case.all_objects.select_for_update().get(pk=case.pk)
    batch = CaseArchiveBatch.objects.select_for_update().get(pk=batch.pk)

    if batch.case_id != case.id:
        raise ValidationError("Батч архивации не соответствует этому делу.")

    if batch.status != "archived":
        raise ValidationError("Батч архивации уже восстановлен или неактивен.")

    if case.archived_at is None:
        raise ValidationError("Дело не находится в архивном состоянии.")

    if case.client.archived_at is not None and not allow_when_client_archived:
        raise ValidationError("Нельзя восстановить отдельное дело, пока клиент заархивирован.")

    case.archived_at = None
    case.archived_by = None
    case.save(update_fields=["archived_at", "archived_by"])

    StaffTask.objects.filter(
        case=case,
        suspended_by_archive_batch=batch,
        suspended_by_case_archive=True
    ).update(
        suspended_by_case_archive=False,
        suspended_at=None,
        suspended_by_archive_batch=None
    )

    batch.status = "restored"
    batch.restored_by = actor
    batch.restored_at = timezone.now()
    batch.save(update_fields=["status", "restored_by", "restored_at"])

    from clients.services.activity import log_client_activity
    log_client_activity(
        client=case.client,
        case=case,
        actor=actor,
        event_type="case_restored",
        summary="Дело восстановлено",
        metadata={
            "case_id": str(case.uuid),
            "archive_batch_uuid": str(batch.uuid),
            "status_tag": "restored",
        }
    )

    return case


@transaction.atomic
def archive_client_with_all_cases(
    client: Client,
    actor: Any,
    confirmed: bool = False,
) -> ClientArchiveBatch:
    if not has_archive_permission(actor):
        raise PermissionDenied("У вас нет прав для архивации клиентов.")

    client = Client.all_objects.select_for_update().get(pk=client.pk)

    if client.archived_at is not None:
        raise ValidationError("Клиент уже заархивирован.")

    if ClientArchiveBatch.objects.filter(client=client, status="archived").exists():
        raise ValidationError("Активная архивация для этого клиента уже существует.")

    active_cases = list(client.cases.filter(archived_at__isnull=True))
    if active_cases and not confirmed:
        raise ValidationError("Нельзя архивировать клиента с активными делами без подтверждения.")

    client_batch = ClientArchiveBatch.objects.create(
        client=client,
        archived_by=actor,
        status="archived",
    )

    for case in active_cases:
        archive_case(case, actor, client_batch=client_batch)

    # The Client model has no archived_by field; the ClientArchiveBatch records
    # who archived the client.
    client.archived_at = timezone.now()
    client.save(update_fields=["archived_at"])

    from clients.services.activity import log_client_activity
    log_client_activity(
        client=client,
        actor=actor,
        event_type="client_archived",
        summary="Клиент заархивирован",
        metadata={
            "archive_batch_uuid": str(client_batch.uuid),
            "status_tag": "archived",
        }
    )

    return client_batch


@transaction.atomic
def restore_client_with_all_cases(
    client: Client,
    actor: Any,
    batch: ClientArchiveBatch,
) -> list[CaseArchiveBatch]:
    if not has_archive_permission(actor):
        raise PermissionDenied("У вас нет прав для восстановления клиентов.")

    client = Client.all_objects.select_for_update().get(pk=client.pk)
    batch = ClientArchiveBatch.objects.select_for_update().get(pk=batch.pk)

    if batch.client_id != client.pk:
        raise ValidationError("Батч архивации не соответствует этому клиенту.")
    if batch.status != "archived":
        raise ValidationError("Батч архивации уже восстановлен.")
    if client.archived_at is None:
        raise ValidationError("Клиент не находится в архивном состоянии.")

    client.archived_at = None
    client.save(update_fields=["archived_at"])

    case_batches = list(batch.case_batches.filter(status="archived"))

    for case_batch in case_batches:
        restore_case(
            case=case_batch.case,
            actor=actor,
            batch=case_batch,
            allow_when_client_archived=True
        )

    batch.status = "restored"
    batch.restored_by = actor
    batch.restored_at = timezone.now()
    batch.save(update_fields=["status", "restored_by", "restored_at"])

    from clients.services.activity import log_client_activity
    log_client_activity(
        client=client,
        actor=actor,
        event_type="client_restored",
        summary="Клиент восстановлен",
        metadata={
            "archive_batch_uuid": str(batch.uuid),
            "status_tag": "restored",
        }
    )

    return case_batches
