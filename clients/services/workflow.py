from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.utils.translation import gettext as _

if TYPE_CHECKING:
    from clients.models.client import Client

WORKFLOW_SEQUENCE = (
    "new_client",
    "document_collection",
    "application_submitted",
    "fingerprints",
    "waiting_decision",
    "decision_received",
    "closed",
)


@dataclass(frozen=True)
class WorkflowValidationResult:
    allowed: bool
    message: str = ""


def validate_client_workflow_transition(*, client: Client, previous_stage: str | None, next_stage: str | None) -> WorkflowValidationResult:
    if not previous_stage or not next_stage or previous_stage == next_stage:
        return WorkflowValidationResult(True)

    try:
        previous_index = WORKFLOW_SEQUENCE.index(previous_stage)
        next_index = WORKFLOW_SEQUENCE.index(next_stage)
    except ValueError:
        return WorkflowValidationResult(True)

    if next_index <= previous_index:
        return WorkflowValidationResult(True)

    if next_stage == "application_submitted":
        if not getattr(client, "pk", None):
            return WorkflowValidationResult(
                False,
                _("Сначала сохраните клиента, затем загрузите обязательные документы и переведите его к этапу подачи."),
            )

        checklist = client.get_document_checklist(check_file_existence=True)
        missing_required = [
            item
            for item in checklist
            if item.get("is_required", True)
            and not item.get("is_custom_submission")
            and not item.get("is_complete")
        ]
        if missing_required:
            return WorkflowValidationResult(
                False,
                _("Нельзя перейти к подаче, пока не собраны обязательные документы."),
            )

    if next_stage == "fingerprints" and not client.submission_date:
        return WorkflowValidationResult(
            False,
            _("Нельзя перейти к этапу отпечатков без даты подачи."),
        )

    if next_stage == "waiting_decision" and not client.fingerprints_date:
        return WorkflowValidationResult(
            False,
            _("Нельзя перейти к ожиданию решения без даты отпечатков."),
        )

    if next_stage in {"decision_received", "closed"} and not client.decision_date:
        return WorkflowValidationResult(
            False,
            _("Нельзя перейти к решению без даты решения."),
        )

    if next_stage == "closed" and getattr(client, "pk", None):
        has_open_payments = client.payments.filter(status__in=["pending", "partial"]).exists()
        if has_open_payments:
            return WorkflowValidationResult(
                False,
                _("Cannot close a case while pending or partial payments exist."),
            )

    return WorkflowValidationResult(True)
