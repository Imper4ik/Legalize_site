from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from django.db import transaction

from clients.models import Client, StaffTask
from clients.services.activity import log_client_activity


@dataclass(frozen=True)
class TaskScenarioResult:
    client: Client
    task: StaffTask
    created: bool = False
    completed: bool = False


def create_task_for_client(
    *,
    client: Client,
    actor,
    cleaned_data: Mapping[str, object],
) -> TaskScenarioResult:
    with transaction.atomic():
        task = StaffTask(client=client, created_by=actor)
        for field in ("title", "description", "due_date", "priority", "status", "assignee", "document", "payment"):
            if field in cleaned_data:
                setattr(task, field, cleaned_data[field])
        if task.assignee_id is None:
            task.assignee = actor
        task.save()

        log_client_activity(
            client=client,
            actor=actor,
            event_type="task_created",
            summary=f"Создана задача: {task.title}",
            details=task.description,
            metadata={
                "priority": task.priority,
                "status": task.status,
                "assignee_id": task.assignee_id,
                "due_date": task.due_date.isoformat() if task.due_date else "",
            },
            task=task,
        )
    return TaskScenarioResult(client=client, task=task, created=True)


def complete_task_for_client(*, task: StaffTask, actor) -> TaskScenarioResult:
    with transaction.atomic():
        locked_task = (
            StaffTask.objects.select_for_update()
            .select_related("client")
            .get(pk=task.pk)
        )
        if locked_task.status == "done":
            return TaskScenarioResult(client=locked_task.client, task=locked_task, completed=False)

        locked_task.mark_done()
        log_client_activity(
            client=locked_task.client,
            actor=actor,
            event_type="task_completed",
            summary=f"Задача завершена: {locked_task.title}",
            metadata={"task_id": locked_task.pk},
            task=locked_task,
        )
        task.status = locked_task.status
        task.completed_at = locked_task.completed_at
        return TaskScenarioResult(client=locked_task.client, task=locked_task, completed=True)
