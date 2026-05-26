from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from django.core.exceptions import ValidationError

from clients.models import Client
from clients.services.workflow import validate_client_workflow_transition
from clients.services.activity import log_client_activity


@dataclass
class WorkflowTransitionResult:
    ok: bool
    message: str = ""


def transition_client_workflow(*, client: Client, target_stage: str, actor: Any = None, submission_date: date | None = None, fingerprints_date: date | None = None, decision_date: date | None = None, save: bool = True) -> WorkflowTransitionResult:
    if submission_date is not None:
        client.submission_date = submission_date
    if fingerprints_date is not None:
        client.fingerprints_date = fingerprints_date
    if decision_date is not None:
        client.decision_date = decision_date

    validation = validate_client_workflow_transition(client=client, previous_stage=client.workflow_stage, next_stage=target_stage)
    if not validation.allowed:
        raise ValidationError(validation.message)

    old_stage = client.workflow_stage
    client.workflow_stage = target_stage
    if save:
        fields = ["workflow_stage", "updated_at"]
        if submission_date is not None:
            fields.append("submission_date")
        if fingerprints_date is not None:
            fields.append("fingerprints_date")
        if decision_date is not None:
            fields.append("decision_date")
        client.save(update_fields=fields)
        log_client_activity(
            client=client,
            actor=actor,
            event_type="workflow_stage_changed",
            summary=f"Workflow stage changed: {old_stage} -> {target_stage}",
            metadata={"old_stage": old_stage, "new_stage": target_stage},
        )
    return WorkflowTransitionResult(ok=True)
