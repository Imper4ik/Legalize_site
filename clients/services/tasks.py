from __future__ import annotations

from datetime import date, timedelta

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
        priority="high" if task_type in ("document_review", "case_number_missing", "deadline_check") else "medium",
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

    updated_count = 0
    for task in tasks:
        task.mark_done()
        updated_count += 1
    return updated_count
