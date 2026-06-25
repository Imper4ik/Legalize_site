from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from django.core.exceptions import ValidationError

from clients.models import Case, Client
from clients.services.activity import log_client_activity
from clients.services.workflow import validate_case_workflow_transition


@dataclass
class WorkflowTransitionResult:
    ok: bool
    message: str = ""


def transition_case_workflow(*, case: Case, target_stage: str, actor: Any = None, submission_date: date | None = None, fingerprints_date: date | None = None, decision_date: date | None = None, save: bool = True) -> WorkflowTransitionResult:
    if submission_date is not None:
        case.submission_date = submission_date
    if fingerprints_date is not None:
        case.fingerprints_date = fingerprints_date
    if decision_date is not None:
        case.decision_date = decision_date

    validation = validate_case_workflow_transition(case=case, previous_stage=case.workflow_stage, next_stage=target_stage)
    if not validation.allowed:
        raise ValidationError(validation.message)

    case.workflow_stage = target_stage
    if save:
        fields = ["workflow_stage"]
        if submission_date is not None:
            fields.append("submission_date")
        if fingerprints_date is not None:
            fields.append("fingerprints_date")
        if decision_date is not None:
            fields.append("decision_date")
        case.save(update_fields=fields)
        log_client_activity(
            client=case.client,
            case=case,
            actor=actor,
            event_type="workflow_stage_changed",
            summary="Этап дела изменён",
            metadata={"case_id": str(case.uuid), "changed_fields": ["workflow_stage"]},
        )
    return WorkflowTransitionResult(ok=True)


def transition_client_workflow(*, client: Client, target_stage: str, actor: Any = None, submission_date: date | None = None, fingerprints_date: date | None = None, decision_date: date | None = None, save: bool = True) -> WorkflowTransitionResult:
    """DEPRECATED compatibility shim. Transition the client's single case.

    Process state (workflow stage, submission/fingerprints/decision dates) lives
    on the case, so this shim no longer mirrors it onto the Client. It resolves
    the client's single active case and delegates to
    :func:`transition_case_workflow`, raising (via the resolver) when the client
    has zero or several active cases — callers with a known case must call
    ``transition_case_workflow`` directly (spec §4).
    """
    from clients.services.cases import get_primary_case_for_client
    case = get_primary_case_for_client(client)
    return transition_case_workflow(
        case=case,
        target_stage=target_stage,
        actor=actor,
        submission_date=submission_date,
        fingerprints_date=fingerprints_date,
        decision_date=decision_date,
        save=save,
    )
