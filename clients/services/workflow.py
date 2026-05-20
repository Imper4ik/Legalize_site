from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from clients.models import DocumentRequirement

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
                "Сначала сохраните клиента, затем загрузите обязательные документы и переведите его к этапу подачи.",
            )

        purpose = client.get_document_requirement_purpose()
        has_db_records = DocumentRequirement.objects.filter(application_purpose=purpose).exists()
        required_codes = set(
            item["code"]
            for item in DocumentRequirement.catalog_for(
                purpose,
                getattr(client, "language", None),
                include_optional=False,
                include_fallback=not has_db_records,
            )
        )
        uploaded_codes = set(client.documents.values_list("document_type", flat=True))
        submitted_codes = set(client.get_submitted_document_codes())
        missing_required = required_codes - uploaded_codes - submitted_codes
        if missing_required:
            return WorkflowValidationResult(
                False,
                "Нельзя перейти к подаче, пока не собраны обязательные документы.",
            )

    if next_stage == "fingerprints" and not client.submission_date:
        return WorkflowValidationResult(
            False,
            "Нельзя перейти к этапу отпечатков без даты подачи.",
        )

    if next_stage == "waiting_decision" and not client.fingerprints_date:
        return WorkflowValidationResult(
            False,
            "Нельзя перейти к ожиданию решения без даты отпечатков.",
        )

    if next_stage in {"decision_received", "closed"} and not client.decision_date:
        return WorkflowValidationResult(
            False,
            "Нельзя завершить этап решения без даты решения.",
        )

    if next_stage == "closed" and getattr(client, "pk", None):
        has_open_payments = client.payments.filter(status__in=["pending", "partial"]).exists()
        if has_open_payments:
            return WorkflowValidationResult(
                False,
                "Cannot close a case while pending or partial payments exist.",
            )

    return WorkflowValidationResult(True)
