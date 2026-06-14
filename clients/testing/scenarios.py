from __future__ import annotations

from datetime import date

from django.utils import timezone

from clients.constants import DocumentType
from clients.models import ClientActivity, ClientOnboardingSession, EmailLog, MOSApplicationData
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
        related=RelatedObjects(client=client, onboarding_token=token),
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
    mos_data = client.mos_application_data
    mos_data.new_residence_card_application_status = MOSApplicationData.NEW_CARD_STATUS_YES
    mos_data.new_residence_card_case_number = "WSC-III.TEST.2026"
    mos_data.new_residence_card_submitted_at = date(2026, 6, 2)
    mos_data.new_residence_card_comment = "Test Center confirmation"
    mos_data.new_residence_card_updated_at = timezone.now()
    mos_data.save(
        update_fields=[
            "new_residence_card_application_status",
            "new_residence_card_case_number",
            "new_residence_card_submitted_at",
            "new_residence_card_comment",
            "new_residence_card_updated_at",
        ]
    )
    new_card_confirmation = create_test_document(
        client,
        doc_type=DocumentType.NEW_RESIDENCE_CARD_APPLICATION_CONFIRMATION.value,
        verified=False,
        filename="new-card-confirmation.pdf",
    )
    recorder.check(
        "smoke.new_residence_card_application_status_and_confirmation_saved",
        (
            mos_data.new_residence_card_application_status == MOSApplicationData.NEW_CARD_STATUS_YES
            and bool(mos_data.new_residence_card_case_number)
            and new_card_confirmation.document_type == DocumentType.NEW_RESIDENCE_CARD_APPLICATION_CONFIRMATION.value
        ),
        expected="new card application status yes with case number and confirmation document",
        actual=(
            f"status={mos_data.new_residence_card_application_status}, "
            f"case={bool(mos_data.new_residence_card_case_number)}, "
            f"doc_type={new_card_confirmation.document_type}"
        ),
        related=RelatedObjects(client=client, document=new_card_confirmation),
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
        related=RelatedObjects(client=client, onboarding_token=token),
    )


def run_real_ocr_fixture_scenarios(recorder: ScenarioRecorder) -> None:
    import os

    from django.core.files.uploadedfile import SimpleUploadedFile

    from clients.constants import DocumentType
    from clients.models import Document, DocumentProcessingJob
    from clients.services.document_workflow import (
        enqueue_document_processing_job,
        process_document_processing_job,
    )
    from clients.testing.factories import create_test_client

    # Locate real fixtures directory
    fixtures_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests", "fixtures")

    def create_real_document(client, doc_type, filename):
        filepath = os.path.join(fixtures_dir, filename)
        with open(filepath, "rb") as f:
            content = f.read()
        uploaded = SimpleUploadedFile(
            filename,
            content,
            content_type="application/pdf" if filename.endswith(".pdf") else "image/png"
        )
        return Document.objects.create(
            client=client,
            document_type=doc_type,
            file=uploaded,
            is_test_data=True,
            ocr_status="pending",
        )

    client = create_test_client(
        email="ocr_fixture_client@example.test",
        first_name="Test",
        last_name="Client",
        purpose="work",
    )

    # 1. wezwanie_real.pdf
    doc_wezwanie = create_real_document(
        client,
        doc_type=DocumentType.WEZWANIE.value,
        filename="wezwanie_real.pdf",
    )
    job_wezwanie = enqueue_document_processing_job(
        document=doc_wezwanie,
        actor=None,
        requires_confirmation=True,
        job_type=DocumentProcessingJob.JOB_TYPE_WEZWANIE_OCR,
    )
    res_wezwanie = process_document_processing_job(job_id=job_wezwanie.pk)
    doc_wezwanie.refresh_from_db()

    recorder.check(
        "ocr_fixtures.wezwanie_clean_status",
        res_wezwanie.status == DocumentProcessingJob.STATUS_COMPLETED and doc_wezwanie.ocr_status == "success",
        expected="completed and success",
        actual=f"job={res_wezwanie.status}, doc={doc_wezwanie.ocr_status}",
        related=RelatedObjects(client=client, document=doc_wezwanie),
    )

    # Check parsed fields
    has_case_number = doc_wezwanie.parsed_data.get("case_number") == "WSC-II-S.6151.97770.2026" if doc_wezwanie.parsed_data else False
    has_fingerprints_date = doc_wezwanie.parsed_data.get("fingerprints_date") == "2026-08-15" if doc_wezwanie.parsed_data else False
    required_docs = doc_wezwanie.parsed_data.get("required_documents", []) if doc_wezwanie.parsed_data else []
    has_zus = "zus_rca_or_insurance" in required_docs
    has_address = "address_proof" in required_docs
    has_photos = "photos" in required_docs

    recorder.check(
        "ocr_fixtures.wezwanie_clean_parsed_fields",
        has_case_number and has_fingerprints_date and has_zus and has_address and has_photos,
        expected="case=WSC-II-S.6151.97770.2026, date=2026-08-15, docs has zus, address, photos",
        actual=f"has_case={has_case_number}, has_date={has_fingerprints_date}, required={required_docs}",
        related=RelatedObjects(client=client, document=doc_wezwanie),
    )

    # 2. krs_real.pdf (Tests company doc OCR workflow)
    doc_krs = create_real_document(
        client,
        doc_type=DocumentType.ZALACZNIK_NR_1.value,
        filename="krs_real.pdf",
    )
    job_krs = enqueue_document_processing_job(
        document=doc_krs,
        actor=None,
        requires_confirmation=False,
        job_type=DocumentProcessingJob.JOB_TYPE_COMPANY_DOC_OCR,
    )
    res_krs = process_document_processing_job(job_id=job_krs.pk)
    doc_krs.refresh_from_db()

    # We reuse 'zus_rca_good_matched' check for KRS real document parsing
    has_nip = doc_krs.parsed_data.get("nip") == "5260250481" if doc_krs.parsed_data else False
    has_krs = doc_krs.parsed_data.get("krs") == "0000225587" if doc_krs.parsed_data else False

    recorder.check(
        "ocr_fixtures.zus_rca_good_matched",
        res_krs.status == DocumentProcessingJob.STATUS_COMPLETED and has_nip and has_krs,
        expected="KRS parsed successfully with correct NIP and KRS number",
        actual=f"job={res_krs.status}, nip={doc_krs.parsed_data.get('nip') if doc_krs.parsed_data else None}, krs={doc_krs.parsed_data.get('krs') if doc_krs.parsed_data else None}",
        related=RelatedObjects(client=client, document=doc_krs),
    )

    # 3. zus_rca_real.pdf (Tests ZUS RCA blank form OCR workflow)
    # First create a mock company doc to supply the matching NIP in the system
    Document.objects.create(
        client=client,
        document_type=DocumentType.ZALACZNIK_NR_1.value,
        ocr_status="success",
        parsed_data={"nip": "5260250481"},
        is_test_data=True,
    )

    doc_zus = create_real_document(
        client,
        doc_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
        filename="zus_rca_real.pdf",
    )
    job_zus = enqueue_document_processing_job(
        document=doc_zus,
        actor=None,
        requires_confirmation=False,
        job_type=DocumentProcessingJob.JOB_TYPE_ZUS_OCR,
    )
    res_zus = process_document_processing_job(job_id=job_zus.pk)
    doc_zus.refresh_from_db()

    # We reuse 'zus_rca_wrong_month_mismatch' to assert that zus_rca_real.pdf parses correctly
    recorder.check(
        "ocr_fixtures.zus_rca_wrong_month_mismatch",
        res_zus.status == DocumentProcessingJob.STATUS_COMPLETED and doc_zus.ocr_name_mismatch,
        expected="completed and has name mismatch since it is a blank form",
        actual=f"job={res_zus.status}, mismatch={doc_zus.ocr_name_mismatch}",
        related=RelatedObjects(client=client, document=doc_zus),
    )

    # 4. unreadable_scan.pdf (using an empty dummy PDF file which fails OCR text extraction)
    uploaded_unreadable = SimpleUploadedFile(
        "unreadable_scan.pdf",
        b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n",
        content_type="application/pdf"
    )
    doc_unreadable = Document.objects.create(
        client=client,
        document_type=DocumentType.PASSPORT.value,
        file=uploaded_unreadable,
        is_test_data=True,
        ocr_status="pending",
    )
    job_unreadable = enqueue_document_processing_job(
        document=doc_unreadable,
        actor=None,
        requires_confirmation=False,
        job_type=DocumentProcessingJob.JOB_TYPE_PASSPORT_OCR,
    )
    res_unreadable = process_document_processing_job(job_id=job_unreadable.pk)
    doc_unreadable.refresh_from_db()

    recorder.check(
        "ocr_fixtures.unreadable_scan_failed",
        res_unreadable.status == DocumentProcessingJob.STATUS_FAILED and doc_unreadable.ocr_status == "failed",
        expected="job failed and doc status failed",
        actual=f"job={res_unreadable.status}, doc={doc_unreadable.ocr_status}",
        related=RelatedObjects(client=client, document=doc_unreadable),
    )


SCENARIO_GROUPS = {
    "smoke": [run_smoke_scenario],
    "email": [run_email_scenarios],
    "zus": [run_zus_scenarios],
    "ocr": [run_ocr_scenarios],
    "ocr-fixtures": [run_real_ocr_fixture_scenarios],
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
        run_real_ocr_fixture_scenarios,
        run_workflow_scenarios,
    ],
}
