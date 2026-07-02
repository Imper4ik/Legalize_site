from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from django.core.exceptions import ValidationError

from clients.models import Case
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


# The client-level shim ``transition_client_workflow`` is gone (spec §4):
# process state lives on the Case, and every caller now passes the case
# explicitly to :func:`transition_case_workflow`.
