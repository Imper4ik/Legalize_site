from __future__ import annotations

from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from clients.models import Case, Client, Document, Payment, StaffTask


def create_auto_task(
    client: Client,
    task_type: str,
    *,
    document: Document | None = None,
    payment: Payment | None = None,
    case: Case | None = None,
    title: str | None = None,
    description: str | None = None,
    due_date: date | None = None,
) -> StaffTask | None:
    """Create an automated StaffTask if a duplicate open one does not exist.

    ``case`` scopes the task to a specific case. When omitted it is derived from
    the document/payment (by StaffTask.save) or the client's single active case;
    callers operating on a multi-case client must pass it (spec section 1/5).
    """
    if client.archived_at is not None:
        return None

    # Serialize check-then-create against concurrent cron runs (e.g.
    # process_document_jobs racing update_reminders): without this, two workers
    # both pass the `.exists()` check and both insert, producing duplicate auto
    # tasks. Locking the client row makes the existence check and the insert
    # atomic relative to any other auto-task creation for the same client.
    # (select_for_update is a no-op on SQLite used in tests; it locks on
    # PostgreSQL in production.)
    with transaction.atomic():
        Client.all_objects.select_for_update().filter(pk=client.pk).first()

        existing_query = StaffTask.objects.filter(
            client=client,
            task_type=task_type,
            status__in=["open", "in_progress"],
        )
        if document:
            existing_query = existing_query.filter(document=document)
        if payment:
            existing_query = existing_query.filter(payment=payment)
        if case:
            existing_query = existing_query.filter(case=case)

        if existing_query.exists():
            return None

        return _create_auto_task(
            client,
            task_type,
            document=document,
            payment=payment,
            case=case,
            title=title,
            description=description,
            due_date=due_date,
        )


def _create_auto_task(
    client: Client,
    task_type: str,
    *,
    document: Document | None = None,
    payment: Payment | None = None,
    case: Case | None = None,
    title: str | None = None,
    description: str | None = None,
    due_date: date | None = None,
) -> StaffTask:
    if not title:
        titles = {
            "document_review": _("Проверить загруженный документ: %(doc_name)s") % {"doc_name": document.display_name if document else ""},
            "missing_document": _("Запросить недостающий документ"),
            "zus_update": _("Запросить актуальный ZUS RCA"),
            "case_number_missing": _("Запросить номер дела у клиента"),
            "fingerprints_followup": _("Проверить статус дела после отпечатков"),
            "payment_followup": _("Контроль оплаты счёта"),
            "client_question": _("Ответить на вопрос клиента"),
            "deadline_check": _("Контроль дедлайна по везванию"),
            "employer_review": _("Проверить работодателя"),
        }
        title = titles.get(task_type, _("Автоматическая задача"))

    if not due_date:
        due_date = timezone.localdate() + timedelta(days=3)

    task = StaffTask.objects.create(
        client=client,
        task_type=task_type,
        is_auto_created=True,
        title=title,
        description=description or "",
        due_date=due_date,
        priority="high" if task_type in ("document_review", "case_number_missing", "deadline_check", "employer_review") else "medium",
        assignee=None,
        document=document,
        payment=payment,
        case=case,
    )
    return task

def close_auto_task(
    client: Client,
    task_type: str,
    *,
    document: Document | None = None,
    payment: Payment | None = None,
    case: Case | None = None,
) -> int:
    """Mark matching open auto tasks as done."""
    tasks = StaffTask.objects.filter(
        client=client,
        task_type=task_type,
        status__in=["open", "in_progress"],
        is_auto_created=True,
    )
    if document:
        tasks = tasks.filter(document=document)
    if payment:
        tasks = tasks.filter(payment=payment)
    if case:
        tasks = tasks.filter(case=case)

    updated_count = 0
    for task in tasks:
        task.mark_done()
        from clients.services.activity import log_client_activity

        log_client_activity(
            client=task.client,
            case=task.case,
            event_type="task_completed",
            summary="Автоматическая задача закрыта",
            task=task,
        )
        updated_count += 1
    return updated_count
