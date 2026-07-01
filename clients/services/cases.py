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


def resolve_active_case_for_client(client: Client, case_uuid: Any) -> Case | None:
    """Resolve an active case identified by ``case_uuid`` that belongs to ``client``.

    Returns ``None`` when no uuid is supplied or it does not match an active case
    of this client. Used by Case-scoped POST handlers so a payment/task/etc. can
    never be attached to another client's case or an archived one (spec §6).
    ``Case.objects`` already excludes archived cases.
    """
    if not case_uuid:
        return None
    return Case.objects.filter(uuid=case_uuid, client_id=client.id).first()


def create_case_for_client(
    *,
    client: Client,
    actor: AbstractBaseUser | AnonymousUser | None = None,
    **overrides: Any,
) -> Case:
    with transaction.atomic():
        has_existing_case = Case.all_objects.filter(client=client).exists()
        if not has_existing_case:
            legacy_family_role = (
                getattr(client, "family_role", "") or ""
                if getattr(client, "application_purpose", "") == "family"
                else ""
            )
            values = {
                "client": client,
                "status": client.status,
                "workflow_stage": "new_client",
                "application_purpose": client.application_purpose,
                "family_role": legacy_family_role,
                "basis_of_stay": client.basis_of_stay or "",
                "company": client.company,
                "is_test_data": client.is_test_data,
                "is_demo_data": client.is_demo_data,
            }
        else:
            values = {
                "client": client,
                "status": "new",
                "workflow_stage": "new_client",
                "application_purpose": "",
                "family_role": "",
                "basis_of_stay": "",
                "company": None,
                "is_test_data": client.is_test_data,
                "is_demo_data": client.is_demo_data,
            }
        values.update(overrides)
        case = Case(**values)
        case.full_clean()
        case.save()

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


def resolve_single_active_case(client: Client) -> Case | None:
    """Return the client's single active case, or None if zero or several.

    A safe, non-raising accessor for client-level consumers (emails, health
    alerts, upload widgets) that need case-first process data but operate at the
    client level. With several active cases it returns None so the caller can
    skip ambiguous aggregation rather than guess (spec section 4/5).
    """
    active_cases = list(Case.objects.filter(client=client)[:2])
    if len(active_cases) == 1:
        return active_cases[0]
    return None


def get_legacy_compatibility_case(client_id: int, model_name: str) -> Case:
    """
    DEPRECATED: Compatibility fallback that resolves a client's single ACTIVE case.

    Allowed only when the client has exactly one active (non-archived) case. With
    zero active cases (including archived-only) or several active cases it raises,
    never creating a case, guessing one, or binding to an archived case.
    """
    from django.core.exceptions import ValidationError

    from clients.models import Case
    logger.warning(
        "Legacy fallback invoked for model %s, client_id %s. This fallback is deprecated.",
        model_name,
        client_id,
    )
    # Case.objects excludes archived cases, so this only ever returns an active one.
    active_cases = list(Case.objects.filter(client_id=client_id)[:2])
    if len(active_cases) == 1:
        return active_cases[0]
    raise ValidationError("Для этой операции необходимо выбрать дело.")

