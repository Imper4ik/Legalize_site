from __future__ import annotations

from datetime import date

from django.utils import timezone

from clients.constants import DocumentType
from clients.models import ClientActivity, ClientOnboardingSession, EmailLog
from clients.services.notifications import send_missing_documents_email
from clients.services.onboarding_tokens import hash_onboarding_token
from clients.services.workflow_transitions import transition_client_workflow
from clients.testing.assertions import RelatedObjects, ScenarioRecorder
from clients.testing.document_tests import run_document_access_scenarios
from clients.testing.email_tests import run_email_scenarios
from clients.testing.factories import (
    create_onboarding_session,
    create_paid_payment,
    create_test_client,
    create_test_document,
)
from clients.testing.ocr_tests import run_ocr_scenarios
from clients.testing.permission_tests import run_permission_scenarios
from clients.testing.workflow_tests import run_workflow_scenarios
from clients.testing.zus_tests import run_zus_scenarios


def run_smoke_scenario(recorder: ScenarioRecorder) -> None:
    client = create_test_client(
        email="client_work_card@example.test",
        first_name="Smoke",
        last_name="Client",
        purpose="work",
        workflow_stage="document_collection",
    )
    payment = create_paid_payment(client)
    token, session = create_onboarding_session(client)
    resolved_session = ClientOnboardingSession.objects.filter(
        token_hash=hash_onboarding_token(token),
        expires_at__gt=timezone.now(),
    ).exclude(status__in=["revoked", "expired"]).first()
    recorder.check(
        "smoke.invite_link_resolves_expected_client",
        resolved_session is not None and resolved_session.client_id == client.pk,
        expected=f"client_id={client.pk}",
        actual=f"client_id={getattr(resolved_session, 'client_id', None)}",
        related=RelatedObjects(client=client),
    )
    recorder.check(
        "smoke.test_data_flags_set",
        client.is_test_data and payment.is_test_data,
        expected="client/payment are test data",
        actual=f"client={client.is_test_data}, payment={payment.is_test_data}",
        related=RelatedObjects(client=client),
    )

    passport = create_test_document(
        client,
        doc_type=DocumentType.PASSPORT.value,
        verified=True,
        filename="passport.pdf",
    )
    missing_email_sent = send_missing_documents_email(client, weekly_key=f"{client.pk}:smoke:missing")
    email_log = EmailLog.objects.filter(client=client, template_type="missing_documents").first()
    recorder.check(
        "smoke.missing_documents_email_created_for_incomplete_checklist",
        missing_email_sent == 1 and email_log is not None and email_log.is_test_data,
        expected="one test EmailLog for missing documents",
        actual=f"sent={missing_email_sent}, log_id={getattr(email_log, 'pk', None)}",
        related=RelatedObjects(client=client, document=passport),
    )

    transition_client_workflow(
        client=client,
        target_stage="fingerprints",
        submission_date=date(2026, 6, 1),
    )
    client.refresh_from_db()
    activity_exists = ClientActivity.objects.filter(client=client, event_type="workflow_stage_changed").exists()
    recorder.check(
        "smoke.workflow_transition_updates_stage_and_audit",
        client.workflow_stage == "fingerprints" and activity_exists,
        expected="workflow_stage=fingerprints and audit activity exists",
        actual=f"stage={client.workflow_stage}, audit={activity_exists}",
        related=RelatedObjects(client=client),
    )

    session.refresh_from_db()
    recorder.check(
        "smoke.invite_session_not_expired",
        session.expires_at is not None and session.client_id == client.pk,
        expected="active session for smoke client",
        actual=f"status={session.status}, client_id={session.client_id}",
        related=RelatedObjects(client=client),
    )


SCENARIO_GROUPS = {
    "smoke": [run_smoke_scenario],
    "email": [run_email_scenarios],
    "zus": [run_zus_scenarios],
    "ocr": [run_ocr_scenarios],
    "documents": [run_document_access_scenarios],
    "permissions": [run_permission_scenarios],
    "security": [run_permission_scenarios, run_document_access_scenarios],
    "workflow": [run_workflow_scenarios],
    "full": [
        run_smoke_scenario,
        run_document_access_scenarios,
        run_permission_scenarios,
        run_email_scenarios,
        run_zus_scenarios,
        run_ocr_scenarios,
        run_workflow_scenarios,
    ],
}
