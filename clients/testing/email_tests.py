from __future__ import annotations

from datetime import date

from django.core.management import call_command

from clients.models import EmailLog
from clients.services.notifications import send_missing_documents_email
from clients.testing.assertions import RelatedObjects, ScenarioRecorder
from clients.testing.factories import create_test_client, create_test_document


def run_email_scenarios(recorder: ScenarioRecorder) -> None:
    client = create_test_client(
        email="client_missing_documents@example.test",
        first_name="Email",
        last_name="Missing",
        purpose="work",
        workflow_stage="waiting_decision",
    )
    client.fingerprints_date = date(2026, 2, 10)
    client.save(update_fields=["fingerprints_date"])

    other = create_test_client(
        email="client_all_ok@example.test",
        first_name="Other",
        last_name="Client",
        purpose="study",
    )
    other.notes = "INTERNAL-STAFF-NOTE-SHOULD-NOT-LEAK"
    other.save(update_fields=["notes"])

    key = f"{client.pk}:case:{'missing_documents'}:required"
    first_send = send_missing_documents_email(client, weekly_key=key)
    log = EmailLog.objects.filter(client=client, template_type="missing_documents").order_by("-sent_at").first()
    recorder.check(
        "email.missing_documents.sent_for_real_problem",
        first_send == 1 and log is not None,
        expected="one missing_documents email log for the affected test client",
        actual=f"sent={first_send}, log_id={getattr(log, 'pk', None)}",
        related=RelatedObjects(client=client),
    )
    if log is not None:
        recorder.check(
            "email.recipient_is_only_target_client",
            client.email in str(log.recipients) and other.email not in str(log.recipients),
            expected=client.email,
            actual=str(log.recipients),
            related=RelatedObjects(client=client),
        )
        recorder.check(
            "email.body_does_not_include_other_client_or_internal_notes",
            other.email not in str(log.body) and "INTERNAL-STAFF-NOTE-SHOULD-NOT-LEAK" not in str(log.body),
            expected="no other client email and no staff note in body",
            actual=str(log.body)[:500],
            related=RelatedObjects(client=client),
        )
        recorder.check(
            "email.log_is_marked_test_data",
            log.is_test_data,
            expected="EmailLog.is_test_data=True",
            actual=f"EmailLog.is_test_data={log.is_test_data}",
            related=RelatedObjects(client=client),
        )

    duplicate_send = send_missing_documents_email(client, weekly_key=key)
    duplicate_logs = EmailLog.objects.filter(idempotency_key=key).count()
    recorder.check(
        "email.dedupe_prevents_duplicate_reminder",
        duplicate_send == 0 and duplicate_logs == 1,
        expected="second send skipped and only one EmailLog for dedupe key",
        actual=f"sent={duplicate_send}, logs={duplicate_logs}",
        related=RelatedObjects(client=client),
    )

    complete = create_test_client(
        email="client_all_ok_complete@example.test",
        first_name="All",
        last_name="Ok",
        purpose="study",
    )
    for index, item in enumerate(complete.get_document_checklist(), start=1):
        code = item["code"]
        create_test_document(complete, doc_type=code, verified=True, filename=f"complete-{index}.pdf")
    no_problem_send = send_missing_documents_email(complete, weekly_key=f"{complete.pk}:no-problem")
    recorder.check(
        "email.no_missing_documents_no_email",
        no_problem_send == 0,
        expected="no email for complete checklist",
        actual=f"sent={no_problem_send}",
        related=RelatedObjects(client=complete),
    )

    closed = create_test_client(
        email="client_closed_case@example.test",
        first_name="Closed",
        last_name="Case",
        purpose="work",
        workflow_stage="closed",
    )
    before = EmailLog.objects.filter(client=closed).count()
    call_command("update_reminders", "--only", "missing-docs")
    after = EmailLog.objects.filter(client=closed).count()
    recorder.check(
        "email.closed_case_not_processed_by_weekly_missing_docs",
        before == after,
        expected="weekly missing-doc job skips closed cases",
        actual=f"before={before}, after={after}",
        related=RelatedObjects(client=closed),
    )
