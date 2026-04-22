from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from django.db import transaction

from clients.models import Client
from clients.services.activity import changed_field_labels, log_client_activity
from clients.services.notifications import (
    send_expired_documents_email,
    send_required_documents_email,
)

ClientNotificationSender = Callable[[Client], int]

CLIENT_UPDATE_TRACKED_FIELDS = (
    "passport_num",
    "case_number",
    "status",
    "workflow_stage",
    "application_purpose",
    "fingerprints_date",
    "decision_date",
    "notes",
)


@dataclass(frozen=True)
class ClientRecordScenarioResult:
    client: Client
    changed_fields: tuple[str, ...] = field(default_factory=tuple)
    workflow_changed: bool = False
    required_documents_email_sent: bool = False
    expired_documents_email_sent: bool = False


def snapshot_client_update_state(
    client: Client,
    *,
    tracked_fields: tuple[str, ...] = CLIENT_UPDATE_TRACKED_FIELDS,
) -> dict[str, object]:
    return {field: getattr(client, field) for field in tracked_fields}


def finalize_client_creation(
    *,
    client: Client,
    actor,
    send_required_email: ClientNotificationSender = send_required_documents_email,
) -> ClientRecordScenarioResult:
    required_documents_email_sent = bool(send_required_email(client))
    with transaction.atomic():
        log_client_activity(
            client=client,
            actor=actor,
            event_type="client_created",
            summary="Клиент создан",
            metadata={"workflow_stage": client.workflow_stage, "status": client.status},
        )
    return ClientRecordScenarioResult(
        client=client,
        required_documents_email_sent=required_documents_email_sent,
    )


def finalize_client_update(
    *,
    client: Client,
    actor,
    previous_values: Mapping[str, object],
    previous_fingerprints_date,
    new_fingerprints_date,
    send_expired_email: ClientNotificationSender = send_expired_documents_email,
) -> ClientRecordScenarioResult:
    expired_documents_email_sent = False
    if new_fingerprints_date and new_fingerprints_date != previous_fingerprints_date:
        expired_documents_email_sent = bool(send_expired_email(client))

    changed_fields = tuple(
        field
        for field, old_value in previous_values.items()
        if getattr(client, field) != old_value
    )

    workflow_changed = "workflow_stage" in changed_fields

    with transaction.atomic():
        if changed_fields:
            log_client_activity(
                client=client,
                actor=actor,
                event_type="client_updated",
                summary="Обновлены данные клиента",
                details=", ".join(changed_field_labels(client, list(changed_fields))),
                metadata={"changed_fields": list(changed_fields)},
            )

        if "status" in changed_fields:
            log_client_activity(
                client=client,
                actor=actor,
                event_type="client_status_changed",
                summary="Статус клиента изменён",
                details=client.get_status_display(),
                metadata={
                    "old_status": previous_values.get("status"),
                    "new_status": client.status,
                },
            )

        if workflow_changed:
            log_client_activity(
                client=client,
                actor=actor,
                event_type="workflow_changed",
                summary="Этап workflow изменён",
                details=client.get_workflow_stage_display(),
                metadata={
                    "old_workflow_stage": previous_values.get("workflow_stage"),
                    "workflow_stage": client.workflow_stage,
                },
            )

        for field_name, summary in (
            ("fingerprints_date", "Дата отпечатков изменена"),
            ("decision_date", "Дата решения изменена"),
        ):
            if field_name not in changed_fields:
                continue
            old_value = previous_values.get(field_name)
            new_value = getattr(client, field_name)
            log_client_activity(
                client=client,
                actor=actor,
                event_type="deadline_changed",
                summary=summary,
                metadata={
                    "field": field_name,
                    "old_value": old_value.isoformat() if old_value else "",
                    "new_value": new_value.isoformat() if new_value else "",
                },
            )

    return ClientRecordScenarioResult(
        client=client,
        changed_fields=changed_fields,
        workflow_changed=workflow_changed,
        expired_documents_email_sent=expired_documents_email_sent,
    )
