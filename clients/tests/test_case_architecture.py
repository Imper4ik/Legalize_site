from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from clients.constants import DocumentType
from clients.models import Case, CaseArchiveSnapshot, Document, Payment, Reminder, StaffTask
from clients.services.activity import log_client_activity
from clients.services.cases import archive_case, create_case_for_client, restore_case
from clients.testing.factories import build_pdf_upload, create_test_client, create_test_document, create_test_user


class CaseBackfillMigrationTests(TransactionTestCase):
    migrate_from = [("clients", "0095_documentversion_docver_case_version_idx")]
    migrate_to = [("clients", "0096_backfill_cases_and_encrypt_json")]

    def setUp(self) -> None:
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.migrate_from)
        old_apps = self.executor.loader.project_state(self.migrate_from).apps

        Client = old_apps.get_model("clients", "Client")
        Document = old_apps.get_model("clients", "Document")
        Payment = old_apps.get_model("clients", "Payment")

        self.client = Client.objects.create(
            first_name="Legacy",
            last_name="Client",
            email="legacy-client@example.test",
            phone="+48000000000",
            application_purpose="work",
            workflow_stage="document_collection",
            language="en",
            is_test_data=True,
        )
        self.document = Document.objects.create(
            client=self.client,
            document_type=DocumentType.PASSPORT.value,
            file="legacy/passport.pdf",
            parsed_data={"legacy": "json"},
            is_test_data=True,
        )
        self.payment = Payment.objects.create(
            client=self.client,
            service_description="work_service",
            total_amount=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
            status="pending",
            is_test_data=True,
        )

        self.executor.loader.build_graph()
        self.executor.migrate(self.migrate_to)
        self.apps = self.executor.loader.project_state(self.migrate_to).apps

    def tearDown(self) -> None:
        self.executor.migrate(self.migrate_to)
        super().tearDown()

    def test_backfill_creates_primary_case_and_links_existing_records(self) -> None:
        CaseModel = self.apps.get_model("clients", "Case")
        DocumentModel = self.apps.get_model("clients", "Document")
        PaymentModel = self.apps.get_model("clients", "Payment")

        case = CaseModel.objects.get(client_id=self.client.pk)
        document = DocumentModel.objects.get(pk=self.document.pk)
        payment = PaymentModel.objects.get(pk=self.payment.pk)

        self.assertEqual(case.workflow_stage, "document_collection")
        self.assertEqual(document.case_id, case.pk)
        self.assertEqual(payment.case_id, case.pk)


class CaseArchitectureTests(TestCase):
    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(assigned_staff=self.staff)
        self.primary_case = self.client_obj.cases.get()

    def test_new_client_gets_primary_case(self) -> None:
        self.assertEqual(self.client_obj.cases.count(), 1)
        self.assertEqual(self.primary_case.workflow_stage, self.client_obj.workflow_stage)
        self.assertEqual(self.primary_case.assigned_staff, self.staff)

    def test_second_case_keeps_documents_payments_and_reminders_separate(self) -> None:
        second_case = create_case_for_client(
            client=self.client_obj,
            actor=self.staff,
            application_purpose="study",
            workflow_stage="document_collection",
        )
        primary_document = create_test_document(self.client_obj, filename="primary.pdf")
        second_document = Document.objects.create(
            client=self.client_obj,
            case=second_case,
            document_type=DocumentType.PASSPORT.value,
            file=build_pdf_upload("second.pdf"),
            is_test_data=True,
        )
        primary_payment = Payment.objects.create(
            client=self.client_obj,
            service_description="work_service",
            total_amount=Decimal("100.00"),
            status="pending",
        )
        second_payment = Payment.objects.create(
            client=self.client_obj,
            case=second_case,
            service_description="study_service",
            total_amount=Decimal("200.00"),
            status="pending",
        )
        Reminder.objects.create(
            client=self.client_obj,
            case=second_case,
            reminder_type="document",
            title="Second case reminder",
            due_date=timezone.localdate(),
        )

        self.assertEqual(primary_document.case_id, self.primary_case.pk)
        self.assertEqual(primary_payment.case_id, self.primary_case.pk)
        self.assertEqual(list(Document.objects.filter(case=second_case)), [second_document])
        self.assertEqual(list(Payment.objects.filter(case=second_case)), [second_payment])
        self.assertEqual(Reminder.objects.filter(case=second_case).count(), 1)

    def test_archive_and_restore_case_use_snapshots_without_touching_other_cases(self) -> None:
        second_case = create_case_for_client(client=self.client_obj, actor=self.staff, application_purpose="study")
        active_document = create_test_document(self.client_obj, filename="active.pdf")
        other_document = Document.objects.create(
            client=self.client_obj,
            case=second_case,
            document_type=DocumentType.PASSPORT.value,
            file=build_pdf_upload("other.pdf"),
            is_test_data=True,
        )
        archived_document = create_test_document(self.client_obj, filename="archived.pdf")
        archived_document.archive()
        payment = Payment.objects.create(
            client=self.client_obj,
            service_description="work_service",
            total_amount=Decimal("100.00"),
            status="pending",
        )
        inactive_reminder = Reminder.objects.create(
            client=self.client_obj,
            reminder_type="other",
            title="Manual inactive",
            due_date=timezone.localdate(),
            is_active=False,
        )
        task = StaffTask.objects.create(client=self.client_obj, title="Open task", status="open")

        result = archive_case(case=self.primary_case, actor=self.staff)

        self.assertGreater(result.documents_changed, 0)
        self.assertIsNotNone(Document.all_objects.get(pk=active_document.pk).archived_at)
        self.assertIsNone(Document.objects.get(pk=other_document.pk).archived_at)
        self.assertEqual(StaffTask.objects.get(pk=task.pk).status, "cancelled")
        self.assertTrue(CaseArchiveSnapshot.objects.filter(archive_batch_uuid=result.archive_batch_uuid).exists())

        restore_case(case=Case.all_objects.get(pk=self.primary_case.pk), actor=self.staff)
        restore_case(case=Case.objects.get(pk=self.primary_case.pk), actor=self.staff)

        self.assertIsNone(Document.all_objects.get(pk=active_document.pk).archived_at)
        self.assertIsNotNone(Document.all_objects.get(pk=archived_document.pk).archived_at)
        self.assertIsNone(Payment.all_objects.get(pk=payment.pk).archived_at)
        self.assertFalse(Reminder.objects.get(pk=inactive_reminder.pk).is_active)
        self.assertEqual(StaffTask.objects.get(pk=task.pk).status, "open")

    def test_reminder_rejects_mismatched_case_source(self) -> None:
        second_case = create_case_for_client(client=self.client_obj, actor=self.staff, application_purpose="study")
        payment = Payment.objects.create(
            client=self.client_obj,
            service_description="work_service",
            total_amount=Decimal("100.00"),
            status="pending",
        )
        reminder = Reminder(
            client=self.client_obj,
            case=second_case,
            payment=payment,
            reminder_type="payment",
            title="Bad reminder",
            due_date=timezone.localdate(),
        )

        with self.assertRaises(ValidationError):
            reminder.full_clean()

    def test_activity_metadata_sanitizer_removes_pii_and_financial_values(self) -> None:
        activity = log_client_activity(
            client=self.client_obj,
            case=self.primary_case,
            actor=self.staff,
            event_type="client_updated",
            summary="Safe metadata test",
            metadata={
                "case_id": self.primary_case.pk,
                "document_count": 2,
                "email": "client@example.test",
                "total_amount": "999.00",
                "passport_number": "AA123456",
            },
        )

        self.assertEqual(activity.metadata["case_id"], self.primary_case.pk)
        self.assertEqual(activity.metadata["document_count"], 2)
        self.assertNotIn("email", activity.metadata)
        self.assertNotIn("total_amount", activity.metadata)
        self.assertNotIn("passport_number", activity.metadata)

    def test_encrypted_json_field_stores_ciphertext_and_reads_python_value(self) -> None:
        document = create_test_document(self.client_obj, filename="encrypted-json.pdf")
        document.parsed_data = {"passport": "AA123456", "safe": "value"}
        document.save(update_fields=["parsed_data"])

        with connection.cursor() as cursor:
            cursor.execute("SELECT parsed_data FROM clients_document WHERE id = %s", [document.pk])
            raw_value = cursor.fetchone()[0]

        document.refresh_from_db()
        self.assertTrue(str(raw_value).startswith("gAAAA"))
        self.assertNotIn("AA123456", str(raw_value))
        self.assertEqual(document.parsed_data["safe"], "value")
