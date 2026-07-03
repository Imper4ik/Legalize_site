from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from clients.constants import DocumentType
from clients.models import Case, Document, Payment, Reminder, StaffTask
from clients.services.activity import log_client_activity
from clients.services.archive import archive_case, restore_case
from clients.services.cases import create_case_for_client
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
        self.assertEqual(self.primary_case.workflow_stage, self.client_obj.get_effective_workflow_stage())

    def test_second_case_keeps_documents_payments_and_reminders_separate(self) -> None:
        second_case = create_case_for_client(
            client=self.client_obj,
            actor=self.staff,
            application_purpose="study",
            workflow_stage="document_collection",
        )
        primary_document = create_test_document(self.client_obj, filename="primary.pdf", case=self.primary_case)
        second_document = Document.objects.create(
            client=self.client_obj,
            case=second_case,
            document_type=DocumentType.PASSPORT.value,
            file=build_pdf_upload("second.pdf"),
            is_test_data=True,
        )
        primary_payment = Payment.objects.create(
            client=self.client_obj,
            case=self.primary_case,
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
            document=second_document,
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
        active_document = create_test_document(self.client_obj, filename="active.pdf", case=self.primary_case)
        other_document = Document.objects.create(
            client=self.client_obj,
            case=second_case,
            document_type=DocumentType.PASSPORT.value,
            file=build_pdf_upload("other.pdf"),
            is_test_data=True,
        )
        archived_document = create_test_document(self.client_obj, filename="archived.pdf", case=self.primary_case)
        archived_document.archive()
        payment = Payment.objects.create(
            client=self.client_obj,
            case=self.primary_case,
            service_description="work_service",
            total_amount=Decimal("100.00"),
            status="pending",
        )
        inactive_reminder = Reminder.objects.create(
            client=self.client_obj,
            case=self.primary_case,
            reminder_type="other",
            title="Manual inactive",
            due_date=timezone.localdate(),
            is_active=False,
        )
        task = StaffTask.objects.create(client=self.client_obj, case=self.primary_case, title="Open task", status="open")

        result = archive_case(case=self.primary_case, actor=self.staff)

        self.assertEqual(result.status, "archived")
        self.assertEqual(result.case, self.primary_case)
        self.assertIsNotNone(Case.all_objects.get(pk=self.primary_case.pk).archived_at)

        # Documents, Payments, Reminders do not change their state
        self.assertIsNone(Document.all_objects.get(pk=active_document.pk).archived_at)
        self.assertIsNone(Document.objects.get(pk=other_document.pk).archived_at)
        self.assertIsNone(Payment.all_objects.get(pk=payment.pk).archived_at)
        self.assertFalse(Reminder.objects.get(pk=inactive_reminder.pk).is_active)

        # Tasks are suspended
        task_refreshed = StaffTask.objects.get(pk=task.pk)
        self.assertTrue(task_refreshed.suspended_by_case_archive)
        self.assertEqual(task_refreshed.suspended_by_archive_batch, result)

        restore_case(case=Case.all_objects.get(pk=self.primary_case.pk), actor=self.staff, batch=result)

        self.assertIsNone(Case.objects.get(pk=self.primary_case.pk).archived_at)
        self.assertIsNone(Document.all_objects.get(pk=active_document.pk).archived_at)
        self.assertIsNotNone(Document.all_objects.get(pk=archived_document.pk).archived_at)
        self.assertIsNone(Payment.all_objects.get(pk=payment.pk).archived_at)
        self.assertFalse(Reminder.objects.get(pk=inactive_reminder.pk).is_active)

        # Tasks are unsuspended
        task_refreshed = StaffTask.objects.get(pk=task.pk)
        self.assertFalse(task_refreshed.suspended_by_case_archive)
        self.assertIsNone(task_refreshed.suspended_by_archive_batch)

    def test_reminder_rejects_mismatched_case_source(self) -> None:
        second_case = create_case_for_client(client=self.client_obj, actor=self.staff, application_purpose="study")
        payment = Payment.objects.create(
            client=self.client_obj,
            case=self.primary_case,
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
                "case_id": self.primary_case.uuid,
                "document_count": 2,
                "email": "client@example.test",
                "total_amount": "999.00",
                "passport_number": "AA123456",
            },
        )

        self.assertEqual(activity.metadata["case_id"], str(self.primary_case.uuid))
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

    def test_create_case_validation(self) -> None:
        # Create a new client. Note that the post_save signal immediately creates a primary case.
        from clients.testing.factories import create_test_client
        client = create_test_client(purpose="work")

        # Deleting the primary case first to test first case creation rules
        client.cases.all().delete()

        # cannot create family case without family_role
        with self.assertRaises(ValidationError):
            create_case_for_client(
                client=client,
                actor=self.staff,
                application_purpose="family",
                family_role="",
            )

        # cannot create work case with family_role
        with self.assertRaises(ValidationError):
            create_case_for_client(
                client=client,
                actor=self.staff,
                application_purpose="work",
                family_role="sponsor",
            )

        # can create with valid family roles
        for role in ["sponsor", "family_spouse", "family_child"]:
            case = create_case_for_client(
                client=client,
                actor=self.staff,
                application_purpose="family",
                family_role=role,
            )
            self.assertEqual(case.family_role, role)
            # Clean up the case so we can test first case creation for others
            client.cases.all().delete()

        # Re-create a case so we can test second case validation
        create_case_for_client(
            client=client,
            actor=self.staff,
            application_purpose="family",
            family_role="sponsor",
        )

        # second case is validated as strictly as first
        with self.assertRaises(ValidationError):
            create_case_for_client(
                client=client,
                actor=self.staff,
                application_purpose="family",
                family_role="",
            )

    def test_create_case_secondary_defaults_and_view_initial(self) -> None:
        from django.test import RequestFactory

        from clients.models import Case, Client, Company
        from clients.services.cases import create_case_for_client
        from clients.views.cases import CaseCreateView

        company = Company.objects.create(name="Test Company")
        client = Client.objects.create(
            first_name="Sergey",
            last_name="Petrov",
            citizenship="UA",
            phone="+48777777777",
            status="pending",
            application_purpose="work",
            basis_of_stay="visa",
            company=company,
        )

        # Delete auto-created primary case completely
        Case.all_objects.filter(client=client).hard_delete()

        # First case should inherit attributes
        case_a = create_case_for_client(client=client, actor=self.staff)
        self.assertEqual(case_a.status, "pending")
        self.assertEqual(case_a.application_purpose, "work")
        self.assertEqual(case_a.basis_of_stay, "visa")
        self.assertEqual(case_a.company, company)

        # Second case should NOT inherit attributes by default, receiving empty/safe defaults
        case_b = create_case_for_client(client=client, actor=self.staff)
        self.assertEqual(case_b.status, "new")
        self.assertEqual(case_b.application_purpose, "")
        self.assertEqual(case_b.basis_of_stay, "")
        self.assertIsNone(case_b.company)

        # Check that CaseCreateView returns clean initial values for second case
        factory = RequestFactory()
        request = factory.get("/")
        request.user = self.staff

        view = CaseCreateView()
        view.request = request
        view.kwargs = {"pk": client.pk}
        view.client_obj = client

        initial = view.get_initial()
        self.assertEqual(initial["application_purpose"], "")
        self.assertEqual(initial["basis_of_stay"], "")
        self.assertIsNone(initial["company"])
        self.assertEqual(initial["workflow_stage"], "new_client")


class CaseFamilyRoleBackfillMigrationTests(TransactionTestCase):
    migrate_from = [("clients", "0110_case_family_role")]
    migrate_to = [("clients", "0111_backfill_case_family_role")]

    def setUp(self) -> None:
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.migrate_from)
        old_apps = self.executor.loader.project_state(self.migrate_from).apps

        Client = old_apps.get_model("clients", "Client")
        Case = old_apps.get_model("clients", "Case")

        self.single_client = Client.objects.create(
            first_name="Single",
            last_name="Family",
            email="single-family@example.test",
            phone="+48000000001",
            application_purpose="family",
            family_role="family_spouse",
            language="en",
            is_test_data=True,
        )
        self.single_case = Case.objects.create(
            client=self.single_client,
            application_purpose="family",
            family_role="",
            is_test_data=True,
        )
        self.multi_client = Client.objects.create(
            first_name="Multi",
            last_name="Family",
            email="multi-family@example.test",
            phone="+48000000002",
            application_purpose="family",
            family_role="family_child",
            language="en",
            is_test_data=True,
        )
        self.multi_case_a = Case.objects.create(
            client=self.multi_client,
            application_purpose="family",
            family_role="",
            is_test_data=True,
        )
        self.multi_case_b = Case.objects.create(
            client=self.multi_client,
            application_purpose="family",
            family_role="",
            is_test_data=True,
        )
        self.prefilled_client = Client.objects.create(
            first_name="Prefilled",
            last_name="Family",
            email="prefilled-family@example.test",
            phone="+48000000003",
            application_purpose="family",
            family_role="family_child",
            language="en",
            is_test_data=True,
        )
        self.prefilled_case = Case.objects.create(
            client=self.prefilled_client,
            application_purpose="family",
            family_role="sponsor",
            is_test_data=True,
        )

        self.executor.loader.build_graph()
        self.executor.migrate(self.migrate_to)
        self.apps = self.executor.loader.project_state(self.migrate_to).apps

    def tearDown(self) -> None:
        self.executor.migrate(self.migrate_to)
        super().tearDown()

    def test_backfill_copies_role_only_for_single_unambiguous_family_case(self) -> None:
        CaseModel = self.apps.get_model("clients", "Case")

        self.assertEqual(CaseModel.objects.get(pk=self.single_case.pk).family_role, "family_spouse")
        self.assertEqual(CaseModel.objects.get(pk=self.multi_case_a.pk).family_role, "")
        self.assertEqual(CaseModel.objects.get(pk=self.multi_case_b.pk).family_role, "")
        self.assertEqual(CaseModel.objects.get(pk=self.prefilled_case.pk).family_role, "sponsor")


class CaseApplicationPurposeBackfillMigrationTests(TransactionTestCase):
    migrate_from = [("clients", "0121_backfill_reminder_case")]
    migrate_to = [("clients", "0122_backfill_case_application_purpose")]

    def setUp(self) -> None:
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.migrate_from)
        old_apps = self.executor.loader.project_state(self.migrate_from).apps

        Client = old_apps.get_model("clients", "Client")
        Case = old_apps.get_model("clients", "Case")

        self.single_client = Client.objects.create(
            first_name="Single",
            last_name="Purpose",
            email="single-purpose@example.test",
            phone="+48000000011",
            application_purpose="study",
            language="en",
            is_test_data=True,
        )
        self.single_case = Case.objects.create(
            client=self.single_client,
            application_purpose="",
            is_test_data=True,
        )
        self.family_client = Client.objects.create(
            first_name="Family",
            last_name="Purpose",
            email="family-purpose@example.test",
            phone="+48000000012",
            application_purpose="family",
            family_role="family_spouse",
            language="en",
            is_test_data=True,
        )
        self.family_case = Case.objects.create(
            client=self.family_client,
            application_purpose="",
            family_role="",
            is_test_data=True,
        )
        self.multi_client = Client.objects.create(
            first_name="Multi",
            last_name="Purpose",
            email="multi-purpose@example.test",
            phone="+48000000013",
            application_purpose="work",
            language="en",
            is_test_data=True,
        )
        self.multi_case_a = Case.objects.create(
            client=self.multi_client, application_purpose="", is_test_data=True
        )
        self.multi_case_b = Case.objects.create(
            client=self.multi_client, application_purpose="", is_test_data=True
        )
        self.prefilled_client = Client.objects.create(
            first_name="Prefilled",
            last_name="Purpose",
            email="prefilled-purpose@example.test",
            phone="+48000000014",
            application_purpose="study",
            language="en",
            is_test_data=True,
        )
        self.prefilled_case = Case.objects.create(
            client=self.prefilled_client,
            application_purpose="work",
            is_test_data=True,
        )

        self.executor.loader.build_graph()
        self.executor.migrate(self.migrate_to)
        self.apps = self.executor.loader.project_state(self.migrate_to).apps

    def tearDown(self) -> None:
        self.executor.migrate(self.migrate_to)
        super().tearDown()

    def test_backfill_copies_purpose_only_for_single_blank_case(self) -> None:
        CaseModel = self.apps.get_model("clients", "Case")

        self.assertEqual(CaseModel.objects.get(pk=self.single_case.pk).application_purpose, "study")
        family_case = CaseModel.objects.get(pk=self.family_case.pk)
        self.assertEqual(family_case.application_purpose, "family")
        self.assertEqual(family_case.family_role, "family_spouse")
        self.assertEqual(CaseModel.objects.get(pk=self.multi_case_a.pk).application_purpose, "")
        self.assertEqual(CaseModel.objects.get(pk=self.multi_case_b.pk).application_purpose, "")
        self.assertEqual(CaseModel.objects.get(pk=self.prefilled_case.pk).application_purpose, "work")
