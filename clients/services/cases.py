from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.db import transaction

from clients.models import Case, Client
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
    """Legacy compatibility shim: resolve the single case of a client.

    Never creates a case and raises if the client has zero or several cases, so
    legacy business code cannot silently pick or fabricate one (spec section 4).
    New code must pass the case explicitly.
    """
    return get_legacy_compatibility_case(client.pk, "Case")


def get_primary_case_for_client_id(client_id: int) -> Case:
    return get_legacy_compatibility_case(client_id, "Case")


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

        from clients.models.case import CaseParticipant
        CaseParticipant.objects.create(
            case=case,
            client=client,
            role="principal",
        )

        log_client_activity(
            client=client,
            case=case,
            actor=actor,
            event_type="client_updated",
            summary="Создано новое дело клиента",
            metadata={"case_id": str(case.uuid), "workflow_stage": case.workflow_stage, "status": case.status},
        )
    return case


def get_legacy_compatibility_case(client_id: int, model_name: str) -> Case:
    """
    DEPRECATED: Compatibility fallback for legacy records when the client has exactly one Case.
    """
    from django.core.exceptions import ValidationError

    from clients.models import Case
    logger.warning(
        "Legacy fallback invoked for model %s, client_id %d. This fallback is deprecated.",
        model_name,
        client_id,
    )
    cases = list(Case.all_objects.filter(client_id=client_id))
    if len(cases) == 1:
        return cases[0]
    raise ValidationError(f"Case is required for new {model_name} objects (client has {len(cases)} cases).")

