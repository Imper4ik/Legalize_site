from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError

from clients.constants import DocumentType
from clients.models import ClientActivity
from clients.services.workflow_transitions import transition_client_workflow
from clients.testing.assertions import RelatedObjects, ScenarioRecorder
from clients.testing.factories import (
    create_paid_payment,
    create_pending_payment,
    create_test_client,
    create_test_document,
)


def run_workflow_scenarios(recorder: ScenarioRecorder) -> None:
    client = create_test_client(
        email="client_workflow@example.test",
        first_name="Workflow",
        last_name="Client",
        workflow_stage="new_client",
    )
    try:
        transition_client_workflow(client=client, target_stage="decision_received")
        rejected = False
    except ValidationError:
        rejected = True
    recorder.check(
        "workflow.rejects_new_to_decision_without_required_dates",
        rejected,
        expected="ValidationError",
        actual="transition accepted" if not rejected else "transition rejected",
        related=RelatedObjects(client=client),
    )

    paid_client = create_test_client(
        email="client_workflow_paid@example.test",
        first_name="Workflow",
        last_name="Paid",
        workflow_stage="document_collection",
    )
    create_paid_payment(paid_client)
    transition_client_workflow(
        client=paid_client,
        target_stage="fingerprints",
        submission_date=date(2026, 6, 1),
    )
    transition_client_workflow(
        client=paid_client,
        target_stage="waiting_decision",
        fingerprints_date=date(2026, 6, 5),
    )
    paid_client.refresh_from_db()
    activity_exists = ClientActivity.objects.filter(
        client=paid_client,
        event_type="workflow_stage_changed",
    ).exists()
    recorder.check(
        "workflow.allowed_transition_writes_audit_activity",
        paid_client.get_effective_workflow_stage() == "waiting_decision" and activity_exists,
        expected="stage waiting_decision and audit activity exists",
        actual=f"stage={paid_client.get_effective_workflow_stage()}, audit={activity_exists}",
        related=RelatedObjects(client=paid_client),
    )

    pending = create_test_client(
        email="client_payment_pending@example.test",
        first_name="Payment",
        last_name="Pending",
    )
    create_pending_payment(pending, service_description="work_service")
    government_fee = create_test_document(
        pending,
        doc_type=DocumentType.PAYMENT_CONFIRMATION.value,
        verified=True,
        filename="government-fee.pdf",
    )
    service_paid = pending.payments.filter(status="paid").exists()
    recorder.check(
        "payments.government_fee_document_does_not_mark_service_paid",
        not service_paid,
        expected="no paid service Payment after uploading government fee document",
        actual=f"paid_payment_exists={service_paid}",
        related=RelatedObjects(client=pending, document=government_fee),
    )

