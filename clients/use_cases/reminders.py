from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from clients.models import Client, Reminder
from clients.services.activity import log_client_activity
from clients.services.notifications import send_expiring_documents_email as default_reminder_notifier

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

ReminderNotifier = Callable[..., int]


@dataclass(frozen=True)
class ReminderScenarioResult:
    client: Client
    reminder: Reminder | None = None
    email_sent: bool = False
    affected_documents_count: int = 0
    emails_sent_count: int = 0
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
    notification_sender: ReminderNotifier = default_reminder_notifier,
) -> ReminderScenarioResult:
    documents = []
    if reminder.document and reminder.document.expiry_date and reminder.case_id:
        documents.append(reminder.document)

    sent_count = int(
        notification_sender(reminder.client, documents, sent_by=actor, case=reminder.case) or 0
    ) if documents else 0
    return ReminderScenarioResult(
        client=reminder.client,
        reminder=reminder,
        email_sent=bool(sent_count),
        affected_documents_count=len(documents),
        emails_sent_count=sent_count,
    )


def send_document_reminder_for_client(
    *,
    client: Client,
    actor: AbstractBaseUser | AnonymousUser | None,
    notification_sender: ReminderNotifier = default_reminder_notifier,
) -> ReminderScenarioResult:
    reminders = (
        client.reminders.filter(reminder_type="document", is_active=True)
        .select_related("document", "document__case")
    )
    documents_by_case: dict[int, list[Any]] = defaultdict(list)
    for reminder in reminders:
        document = reminder.document
        if document is None or document.expiry_date is None or document.case_id is None:
            continue
        documents_by_case[document.case_id].append(document)

    sent_count = 0
    affected_documents_count = 0
    for documents in documents_by_case.values():
        case = documents[0].case
        if case is None:
            continue
        sent_count += int(notification_sender(client, documents, sent_by=actor, case=case) or 0)
        affected_documents_count += len(documents)

    return ReminderScenarioResult(
        client=client,
        email_sent=bool(sent_count),
        affected_documents_count=affected_documents_count,
        emails_sent_count=sent_count,
    )
