from __future__ import annotations

from datetime import date

from clients.constants import DocumentType
from clients.models import DocumentProcessingJob, EmailLog
from clients.services.document_workflow import (
    enqueue_document_processing_job,
    process_document_processing_job,
)
from clients.services.wezwanie_parser import WezwanieData
from clients.testing.assertions import RelatedObjects, ScenarioRecorder
from clients.testing.factories import create_test_client, create_test_document


def run_ocr_scenarios(recorder: ScenarioRecorder) -> None:
    client = create_test_client(
        email="client_wezwanie_ocr@example.test",
        first_name="Test",
        last_name="Client",
        purpose="work",
    )
    document = create_test_document(
        client,
        doc_type=DocumentType.WEZWANIE.value,
        filename="wezwanie-clean.pdf",
    )
    before_emails = EmailLog.objects.filter(client=client).count()
    job = enqueue_document_processing_job(
        document=document,
        actor=None,
        requires_confirmation=True,
        job_type=DocumentProcessingJob.JOB_TYPE_WEZWANIE_OCR,
    )

    def fake_parser(_path: str) -> WezwanieData:
        return WezwanieData(
            text="WEZWANIE Test Client WSC-II-S.6151.97770.2026",
            case_number="WSC-II-S.6151.97770.2026",
            fingerprints_date=date(2026, 6, 15),
            full_name="Test Client",
            required_documents=[DocumentType.ZUS_RCA_OR_INSURANCE.value, DocumentType.EMPLOYMENT_CONTRACT.value],
        )

    result = process_document_processing_job(
        job_id=job.pk,
        parser=fake_parser,
        send_missing_email=lambda _client: 1,
        send_appointment_email=lambda _client: 1,
    )
    document.refresh_from_db()
    client.refresh_from_db()
    after_emails = EmailLog.objects.filter(client=client).count()

    recorder.check(
        "ocr.wezwanie_job_completes_and_requires_staff_confirmation",
        result.status == DocumentProcessingJob.STATUS_COMPLETED and document.awaiting_confirmation,
        expected="completed job and document.awaiting_confirmation=True",
        actual=f"status={result.status}, awaiting_confirmation={document.awaiting_confirmation}",
        related=RelatedObjects(client=client, document=document),
    )
    recorder.check(
        "ocr.no_client_updates_before_staff_confirmation",
        not client.effective_case_number and not client.effective_fingerprints_date,
        expected="case_number and fingerprints_date unchanged",
        actual=f"case_number={client.effective_case_number}, fingerprints_date={client.effective_fingerprints_date}",
        related=RelatedObjects(client=client, document=document),
    )
    recorder.check(
        "ocr.no_email_before_staff_confirmation",
        before_emails == after_emails,
        expected="no EmailLog before staff confirmation",
        actual=f"before={before_emails}, after={after_emails}",
        related=RelatedObjects(client=client, document=document),
    )

