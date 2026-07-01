from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.db import transaction

from clients.models import Client
from clients.services.activity import changed_field_labels, log_client_activity
from clients.services.notifications import (
    send_expired_documents_email,
    send_required_documents_email,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

ClientNotificationSender = Callable[[Client], int]

CLIENT_UPDATE_TRACKED_FIELDS = (
    # Process state (workflow stage, case number, process dates) lives on the
    # Case now (spec §4); only permanent client attributes are tracked here.
    "passport_num",
    "status",
    "application_purpose",
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
) -> dict[str, Any]:
    return {field: getattr(client, field) for field in tracked_fields}


def finalize_client_creation(
    *,
    client: Client,
    actor: AbstractBaseUser | AnonymousUser | None,
    send_required_email: Any = send_required_documents_email,
) -> ClientRecordScenarioResult:
    import inspect

    from clients.services.cases import resolve_single_active_case

    case = resolve_single_active_case(client)

    supports_case = False
    try:
        sig = inspect.signature(send_required_email)
        supports_case = "case" in sig.parameters
    except (ValueError, TypeError):
        supports_case = False

    if supports_case:
        required_documents_email_sent = bool(send_required_email(client, case=case))
    else:
        required_documents_email_sent = bool(send_required_email(client))
    with transaction.atomic():
        log_client_activity(
            client=client,
            actor=actor,
            event_type="client_created",
            summary="Клиент создан",
            metadata={"workflow_stage": client.get_effective_workflow_stage(), "status": client.status},
        )
    return ClientRecordScenarioResult(
        client=client,
        required_documents_email_sent=required_documents_email_sent,
    )


def finalize_client_update(
    *,
    client: Client,
    actor: AbstractBaseUser | AnonymousUser | None,
    previous_values: Mapping[str, Any],
    send_expired_email: ClientNotificationSender = send_expired_documents_email,
) -> ClientRecordScenarioResult:
    expired_documents_email_sent = False

    # Process state (workflow stage, dates) lives on the Case (spec §4): the
    # client form no longer edits it, so this only tracks permanent attributes.
    changed_fields = tuple(field for field, old_value in previous_values.items() if getattr(client, field) != old_value)

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
                    "old_status": str(previous_values.get("status")),
                    "new_status": client.status,
                },
            )

    return ClientRecordScenarioResult(
        client=client,
        changed_fields=changed_fields,
        workflow_changed=False,
        expired_documents_email_sent=expired_documents_email_sent,
    )
