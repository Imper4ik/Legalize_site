from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from clients.models import Case, CaseArchiveSnapshot, Client, Document, Payment, Reminder, StaffTask
from clients.services.activity import log_client_activity

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaseArchiveResult:
    case: Case
    archive_batch_uuid: UUID
    documents_changed: int = 0
    payments_changed: int = 0
    reminders_changed: int = 0
    tasks_changed: int = 0
    portal_user_changed: bool = False


def get_primary_case_for_client(client: Client) -> Case:
    case, _created = Case.objects.get_or_create_primary_for_client(client)
    return case


def get_primary_case_for_client_id(client_id: int) -> Case:
    case, _created = Case.objects.get_or_create_primary_for_client_id(client_id)
    return case


def create_case_for_client(
    *,
    client: Client,
    actor: AbstractBaseUser | AnonymousUser | None = None,
    **overrides: Any,
) -> Case:
    with transaction.atomic():
        values = {
            "client": client,
            "status": client.status,
            "workflow_stage": client.workflow_stage,
            "application_purpose": client.application_purpose,
            "basis_of_stay": client.basis_of_stay or "",
            "assigned_staff": client.assigned_staff,
            "company": client.company,
            "is_test_data": client.is_test_data,
            "is_demo_data": client.is_demo_data,
        }
        values.update(overrides)
        case = Case.objects.create(**values)
        log_client_activity(
            client=client,
            case=case,
            actor=actor,
            event_type="client_updated",
            summary="Создано новое дело клиента",
            metadata={"case_id": case.pk, "workflow_stage": case.workflow_stage, "status": case.status},
        )
    return case


def _snapshot(
    *,
    case: Case,
    archive_batch_uuid: UUID,
    object_type: str,
    object_id: int,
    created_by: AbstractBaseUser | AnonymousUser | None,
    was_active: bool = True,
    previous_archived_at: Any = None,
    previous_reminder_is_active: bool | None = None,
    previous_task_status: str = "",
    previous_user_is_active: bool | None = None,
) -> None:
    real_actor = created_by if created_by and created_by.is_authenticated else None
    CaseArchiveSnapshot.objects.get_or_create(
        archive_batch_uuid=archive_batch_uuid,
        object_type=object_type,
        object_id=object_id,
        defaults={
            "case": case,
            "client": case.client,
            "was_active": was_active,
            "previous_archived_at": previous_archived_at,
            "previous_reminder_is_active": previous_reminder_is_active,
            "previous_task_status": previous_task_status,
            "previous_user_is_active": previous_user_is_active,
            "created_by": real_actor,
        },
    )


def archive_case(*, case: Case, actor: AbstractBaseUser | AnonymousUser | None = None) -> CaseArchiveResult:
    with transaction.atomic():
        locked_case = Case.all_objects.select_for_update().select_related("client", "client__user").get(pk=case.pk)
        if locked_case.archived_at is not None:
            return CaseArchiveResult(
                case=locked_case,
                archive_batch_uuid=locked_case.last_archive_batch_uuid or uuid4(),
            )

        now = timezone.now()
        archive_batch_uuid = uuid4()
        document_ids = list(
            Document.objects.filter(case=locked_case, archived_at__isnull=True).values_list("pk", flat=True)
        )
        payment_ids = list(
            Payment.objects.filter(case=locked_case, archived_at__isnull=True).values_list("pk", flat=True)
        )
        reminders = list(Reminder.objects.filter(case=locked_case, is_active=True).only("pk", "is_active"))
        tasks = list(StaffTask.objects.filter(case=locked_case, status__in=["open", "in_progress"]).only("pk", "status"))

        for object_id in document_ids:
            _snapshot(
                case=locked_case,
                archive_batch_uuid=archive_batch_uuid,
                object_type=CaseArchiveSnapshot.OBJECT_TYPE_DOCUMENT,
                object_id=object_id,
                previous_archived_at=None,
                created_by=actor,
            )
        for object_id in payment_ids:
            _snapshot(
                case=locked_case,
                archive_batch_uuid=archive_batch_uuid,
                object_type=CaseArchiveSnapshot.OBJECT_TYPE_PAYMENT,
                object_id=object_id,
                previous_archived_at=None,
                created_by=actor,
            )
        for reminder in reminders:
            _snapshot(
                case=locked_case,
                archive_batch_uuid=archive_batch_uuid,
                object_type=CaseArchiveSnapshot.OBJECT_TYPE_REMINDER,
                object_id=reminder.pk,
                previous_reminder_is_active=reminder.is_active,
                created_by=actor,
            )
        for task in tasks:
            _snapshot(
                case=locked_case,
                archive_batch_uuid=archive_batch_uuid,
                object_type=CaseArchiveSnapshot.OBJECT_TYPE_TASK,
                object_id=task.pk,
                previous_task_status=task.status,
                created_by=actor,
            )

        documents_changed = Document.all_objects.filter(pk__in=document_ids).update(archived_at=now)
        payments_changed = Payment.all_objects.filter(pk__in=payment_ids).update(archived_at=now)
        reminders_changed = Reminder.objects.filter(pk__in=[reminder.pk for reminder in reminders]).update(is_active=False)
        tasks_changed = StaffTask.objects.filter(pk__in=[task.pk for task in tasks]).update(status="cancelled", updated_at=now)

        portal_user_changed = False
        user = locked_case.client.user
        active_other_cases = Case.objects.filter(client=locked_case.client).exclude(pk=locked_case.pk).exists()
        if user and not user.is_staff and user.is_active and not active_other_cases:
            _snapshot(
                case=locked_case,
                archive_batch_uuid=archive_batch_uuid,
                object_type=CaseArchiveSnapshot.OBJECT_TYPE_PORTAL_USER,
                object_id=user.pk,
                previous_user_is_active=True,
                created_by=actor,
            )
            user.is_active = False
            user.save(update_fields=["is_active"])
            portal_user_changed = True

        real_actor = actor if actor and actor.is_authenticated else None
        locked_case.archived_at = now
        locked_case.archived_by = real_actor
        locked_case.last_archive_batch_uuid = archive_batch_uuid
        locked_case.save(update_fields=["archived_at", "archived_by", "last_archive_batch_uuid", "updated_at"])

        log_client_activity(
            client=locked_case.client,
            case=locked_case,
            actor=actor,
            event_type="client_updated",
            summary="Дело архивировано",
            metadata={
                "case_id": locked_case.pk,
                "archive_batch_uuid": str(archive_batch_uuid),
                "documents_changed": documents_changed,
                "payments_changed": payments_changed,
                "reminders_changed": reminders_changed,
                "tasks_changed": tasks_changed,
                "portal_user_changed": portal_user_changed,
            },
        )

    return CaseArchiveResult(
        case=locked_case,
        archive_batch_uuid=archive_batch_uuid,
        documents_changed=documents_changed,
        payments_changed=payments_changed,
        reminders_changed=reminders_changed,
        tasks_changed=tasks_changed,
        portal_user_changed=portal_user_changed,
    )


def restore_case(*, case: Case, actor: AbstractBaseUser | AnonymousUser | None = None) -> CaseArchiveResult:
    with transaction.atomic():
        locked_case = Case.all_objects.select_for_update().select_related("client").get(pk=case.pk)
        archive_batch_uuid = locked_case.last_archive_batch_uuid
        if locked_case.archived_at is None or archive_batch_uuid is None:
            return CaseArchiveResult(case=locked_case, archive_batch_uuid=archive_batch_uuid or uuid4())

        snapshots = list(
            CaseArchiveSnapshot.objects.filter(case=locked_case, archive_batch_uuid=archive_batch_uuid)
        )
        documents_changed = payments_changed = reminders_changed = tasks_changed = 0
        portal_user_changed = False

        for snapshot in snapshots:
            if snapshot.object_type == CaseArchiveSnapshot.OBJECT_TYPE_DOCUMENT:
                documents_changed += Document.all_objects.filter(
                    pk=snapshot.object_id,
                    case=locked_case,
                    archived_at__isnull=False,
                ).update(archived_at=snapshot.previous_archived_at)
            elif snapshot.object_type == CaseArchiveSnapshot.OBJECT_TYPE_PAYMENT:
                payments_changed += Payment.all_objects.filter(
                    pk=snapshot.object_id,
                    case=locked_case,
                    archived_at__isnull=False,
                ).update(archived_at=snapshot.previous_archived_at)
            elif snapshot.object_type == CaseArchiveSnapshot.OBJECT_TYPE_REMINDER and snapshot.previous_reminder_is_active is not None:
                reminders_changed += Reminder.objects.filter(pk=snapshot.object_id, case=locked_case).update(
                    is_active=snapshot.previous_reminder_is_active
                )
            elif snapshot.object_type == CaseArchiveSnapshot.OBJECT_TYPE_TASK and snapshot.previous_task_status:
                tasks_changed += StaffTask.objects.filter(pk=snapshot.object_id, case=locked_case).update(
                    status=snapshot.previous_task_status,
                    updated_at=timezone.now(),
                )
            elif snapshot.object_type == CaseArchiveSnapshot.OBJECT_TYPE_PORTAL_USER and snapshot.previous_user_is_active:
                UserModel = get_user_model()
                portal_user_changed = bool(
                    UserModel.objects.filter(pk=snapshot.object_id, is_staff=False).update(is_active=True)
                )

        now = timezone.now()
        Case.all_objects.filter(pk=locked_case.pk).update(
            archived_at=None,
            archived_by=None,
            updated_at=now,
        )
        locked_case.archived_at = None
        locked_case.archived_by = None
        locked_case.updated_at = now
        log_client_activity(
            client=locked_case.client,
            case=locked_case,
            actor=actor,
            event_type="client_updated",
            summary="Дело восстановлено из архива",
            metadata={
                "case_id": locked_case.pk,
                "archive_batch_uuid": str(archive_batch_uuid),
                "documents_changed": documents_changed,
                "payments_changed": payments_changed,
                "reminders_changed": reminders_changed,
                "tasks_changed": tasks_changed,
                "portal_user_changed": portal_user_changed,
            },
        )

    return CaseArchiveResult(
        case=locked_case,
        archive_batch_uuid=archive_batch_uuid,
        documents_changed=documents_changed,
        payments_changed=payments_changed,
        reminders_changed=reminders_changed,
        tasks_changed=tasks_changed,
        portal_user_changed=portal_user_changed,
    )


def archive_all_client_cases(*, client: Client, actor: AbstractBaseUser | AnonymousUser | None = None) -> list[CaseArchiveResult]:
    results = []
    for case in Case.objects.filter(client=client).order_by("id"):
        results.append(archive_case(case=case, actor=actor))
    return results
