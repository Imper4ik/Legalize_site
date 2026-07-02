from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.utils.translation import gettext as _

if TYPE_CHECKING:
    from clients.models.case import Case

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


def validate_case_workflow_transition(*, case: Case, previous_stage: str | None, next_stage: str | None) -> WorkflowValidationResult:
    if not previous_stage or not next_stage or previous_stage == next_stage:
        return WorkflowValidationResult(True)

    try:
        previous_index = WORKFLOW_SEQUENCE.index(previous_stage)
        next_index = WORKFLOW_SEQUENCE.index(next_stage)
    except ValueError:
        return WorkflowValidationResult(True)

    if next_index <= previous_index:
        return WorkflowValidationResult(True)

    # 4. Запретить перевод Case в рабочий статус без principal participant.
    if next_stage != "new_client":
        if not case.participants.filter(role="principal").exists():
            return WorkflowValidationResult(
                False,
                _("Нельзя перевести дело в рабочий статус без главного заявителя."),
            )

    if next_stage == "application_submitted":
        if not getattr(case, "pk", None):
            return WorkflowValidationResult(
                False,
                _("Сначала сохраните дело, затем загрузите обязательные документы и переведите его к этапу подачи."),
            )

        checklist = case.get_document_checklist(check_file_existence=True)
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

    if next_stage == "fingerprints" and not case.submission_date:
        return WorkflowValidationResult(
            False,
            _("Нельзя перейти к этапу отпечатков без даты подачи."),
        )

    if next_stage == "waiting_decision" and not case.fingerprints_date:
        return WorkflowValidationResult(
            False,
            _("Нельзя перейти к ожиданию решения без даты отпечатков."),
        )

    if next_stage in {"decision_received", "closed"} and not case.decision_date:
        return WorkflowValidationResult(
            False,
            _("Нельзя перейти к решению без даты решения."),
        )

    if next_stage == "closed" and getattr(case, "pk", None):
        has_open_payments = case.payments.filter(status__in=["pending", "partial"]).exists()
        if has_open_payments:
            return WorkflowValidationResult(
                False,
                _("Cannot close a case while pending or partial payments exist."),
            )

    return WorkflowValidationResult(True)


# The client-level shim ``validate_client_workflow_transition`` is gone
# (spec §4): workflow policy is validated on the Case via
# :func:`validate_case_workflow_transition`; every caller passes the case.
