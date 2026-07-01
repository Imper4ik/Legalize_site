from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from clients.models import Client, Reminder
from clients.services.activity import log_client_activity
from clients.services.notifications import send_expiring_documents_email

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

DocumentReminderSender = Callable[..., int]


@dataclass(frozen=True)
class ReminderScenarioResult:
    client: Client
    reminder: Reminder | None = None
    email_sent: bool = False
    affected_documents_count: int = 0
    deleted_reminder_id: int | None = None


def _reminder_metadata(reminder: Reminder) -> dict[str, Any]:
    # Only whitelisted, non-PII keys (spec §12). The activity sanitizer would
    # drop the rest, but we avoid building the reminder title/type at all.
    return {"document_id": reminder.document_id}


def delete_reminder(*, reminder: Reminder, actor: AbstractBaseUser | AnonymousUser | None) -> ReminderScenarioResult:
    client = reminder.client
    reminder_id = reminder.pk
    log_client_activity(
        client=client,
        actor=actor,
        event_type="reminder_deleted",
        summary="Напоминание удалено",
        metadata=_reminder_metadata(reminder),
    )
    reminder.delete()
    reminder.pk = reminder_id
    return ReminderScenarioResult(client=client, deleted_reminder_id=reminder_id)


def deactivate_reminder(*, reminder: Reminder, actor: AbstractBaseUser | AnonymousUser | None) -> ReminderScenarioResult:
    reminder.is_active = False
    reminder.save(update_fields=["is_active"])
    log_client_activity(
        client=reminder.client,
        actor=actor,
        event_type="reminder_deactivated",
        summary="Напоминание отмечено выполненным",
        metadata=_reminder_metadata(reminder),
    )
    return ReminderScenarioResult(client=reminder.client, reminder=reminder)


def send_document_reminder_for_reminder(
    *,
    reminder: Reminder,
    actor: AbstractBaseUser | AnonymousUser | None,
    send_email: DocumentReminderSender = send_expiring_documents_email,
) -> ReminderScenarioResult:
    documents = []
    if reminder.document and reminder.document.expiry_date:
        documents.append(reminder.document)

    sent = bool(send_email(reminder.client, documents, sent_by=actor, case=reminder.case))
    return ReminderScenarioResult(
        client=reminder.client,
        reminder=reminder,
        email_sent=sent,
        affected_documents_count=len(documents),
    )


def send_document_reminder_for_client(
    *,
    client: Client,
    actor: AbstractBaseUser | AnonymousUser | None,
    send_email: DocumentReminderSender = send_expiring_documents_email,
) -> ReminderScenarioResult:
    reminders = (
        client.reminders.filter(reminder_type="document", is_active=True)
        .select_related("document")
    )
    documents = [
        reminder.document
        for reminder in reminders
        if reminder.document and reminder.document.expiry_date
    ]

    case = documents[0].case if documents and all(document.case_id == documents[0].case_id for document in documents) else None
    sent = bool(send_email(client, documents, sent_by=actor, case=case))
    return ReminderScenarioResult(
        client=client,
        email_sent=sent,
        affected_documents_count=len(documents),
    )
