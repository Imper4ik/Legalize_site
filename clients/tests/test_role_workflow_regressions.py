from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clients.constants import DocumentType
from clients.models import Client, Document, DocumentRequirement, MOSApplicationData, Payment, Reminder, StaffTask
from clients.services.access import accessible_tasks_queryset
from clients.services.workflow import validate_client_workflow_transition
from clients.services.workflow_transitions import transition_client_workflow
from clients.testing.factories import create_test_client, create_test_document, create_test_user


class StaffRoleRegressionTests(TestCase):
    def setUp(self):
        self.staff = create_test_user(role="Staff")
        self.readonly = create_test_user(role="ReadOnly")
        self.client_obj = create_test_client(workflow_stage="document_collection")

    def test_staff_can_restore_archived_client_with_documents_and_payments(self):
        document = create_test_document(self.client_obj)
        payment = Payment.objects.create(
            client=self.client_obj,
            service_description="work_service",
            total_amount=Decimal("100.00"),
            status="pending",
        )
        self.client_obj.archive()
        self.client.force_login(self.staff)

        response = self.client.post(reverse("clients:client_restore", kwargs={"pk": self.client_obj.pk}))

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(Client.all_objects.get(pk=self.client_obj.pk).archived_at)
        self.assertIsNone(Document.all_objects.get(pk=document.pk).archived_at)
        self.assertIsNone(Payment.all_objects.get(pk=payment.pk).archived_at)

    def test_staff_can_restore_archived_document_and_payment_for_active_client(self):
        document = create_test_document(self.client_obj)
        payment = Payment.objects.create(
            client=self.client_obj,
            service_description="work_service",
            total_amount=Decimal("100.00"),
            status="pending",
        )
        document.archive()
        payment.archive()
        self.client.force_login(self.staff)

        self.assertEqual(self.client.post(reverse("clients:document_restore", kwargs={"pk": document.pk})).status_code, 302)
        self.assertEqual(self.client.post(reverse("clients:payment_restore", kwargs={"pk": payment.pk})).status_code, 302)
        self.assertIsNone(Document.all_objects.get(pk=document.pk).archived_at)
        self.assertIsNone(Payment.all_objects.get(pk=payment.pk).archived_at)

    def test_readonly_cannot_restore_archived_records_or_review_ocr(self):
        document = create_test_document(self.client_obj, doc_type=DocumentType.WEZWANIE.value, awaiting_confirmation=True, ocr_status="success")
        payment = Payment.objects.create(client=self.client_obj, service_description="work_service", total_amount=Decimal("100.00"), status="pending")
        self.client_obj.archive()
        document.archive()
        payment.archive()
        self.client.force_login(self.readonly)
        self.assertEqual(self.client.post(reverse("clients:client_restore", kwargs={"pk": self.client_obj.pk})).status_code, 403)
        self.assertEqual(self.client.post(reverse("clients:document_restore", kwargs={"pk": document.pk})).status_code, 403)
        self.assertEqual(self.client.post(reverse("clients:payment_restore", kwargs={"pk": payment.pk})).status_code, 403)
        document.restore()
        self.assertEqual(self.client.get(reverse("clients:get_document_parsed_data", kwargs={"doc_id": document.pk})).status_code, 403)

    def test_staff_can_review_ocr_without_employee_permission_flag(self):
        document = create_test_document(self.client_obj, doc_type=DocumentType.WEZWANIE.value, awaiting_confirmation=True, ocr_status="success")
        document.parsed_data = {"safe": "value"}
        document.save(update_fields=["parsed_data"])
        self.client.force_login(self.staff)
        response = self.client.get(reverse("clients:get_document_parsed_data", kwargs={"doc_id": document.pk}))
        self.assertEqual(response.status_code, 200)

    def test_staff_cannot_manage_roles_staff_or_critical_settings(self):
        self.client.force_login(self.staff)
        for name in ["clients:role_manage", "clients:staff_manage", "clients:staff_activity_logs", "clients:app_settings"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)


class ClientArchiveCascadeTests(TestCase):
    def setUp(self):
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(workflow_stage="document_collection", assigned_staff=self.staff)

    def test_archiving_client_archives_case_records_and_hides_open_tasks(self):
        document = create_test_document(self.client_obj)
        payment = Payment.objects.create(
            client=self.client_obj,
            service_description="work_service",
            total_amount=Decimal("100.00"),
            amount_paid=Decimal("20.00"),
            status="partial",
            due_date=timezone.localdate(),
        )
        payment_reminder = Reminder.objects.get(payment=payment)
        custom_reminder = Reminder.objects.create(
            client=self.client_obj,
            reminder_type="other",
            title="Manual follow-up",
            due_date=timezone.localdate(),
        )
        task = StaffTask.objects.create(client=self.client_obj, title="Open task", status="open")

        self.client_obj.archive()

        self.assertIsNotNone(Client.all_objects.get(pk=self.client_obj.pk).archived_at)
        self.assertIsNotNone(Document.all_objects.get(pk=document.pk).archived_at)
        self.assertIsNotNone(Payment.all_objects.get(pk=payment.pk).archived_at)
        payment_reminder.refresh_from_db()
        custom_reminder.refresh_from_db()
        self.assertFalse(payment_reminder.is_active)
        self.assertFalse(custom_reminder.is_active)
        self.assertFalse(
            accessible_tasks_queryset(self.staff, StaffTask.objects.all()).filter(pk=task.pk).exists()
        )

    def test_restoring_client_restores_archived_documents_and_payments(self):
        document = create_test_document(self.client_obj)
        payment = Payment.objects.create(
            client=self.client_obj,
            service_description="work_service",
            total_amount=Decimal("100.00"),
            status="pending",
        )
        self.client_obj.archive()

        Client.all_objects.get(pk=self.client_obj.pk).restore()

        self.assertIsNone(Document.all_objects.get(pk=document.pk).archived_at)
        self.assertIsNone(Payment.all_objects.get(pk=payment.pk).archived_at)


class WorkflowDocumentEligibilityTests(TestCase):
    def setUp(self):
        self.client_obj = create_test_client(workflow_stage="document_collection", purpose="other")
        purpose = self.client_obj.get_document_requirement_purpose()
        DocumentRequirement.objects.filter(application_purpose=purpose).delete()
        DocumentRequirement.objects.create(application_purpose=purpose, document_type=DocumentType.PASSPORT.value, is_required=True)

    def _transition_allowed(self):
        return validate_client_workflow_transition(client=self.client_obj, previous_stage="document_collection", next_stage="application_submitted").allowed

    def test_rejected_expired_missing_file_and_archived_documents_block_submission(self):
        cases = [
            {"rejection_reason": "bad"},
            {"expiry_date": timezone.localdate() - timezone.timedelta(days=1)},
            {"delete_file": True},
            {"archive": True},
        ]
        for attrs in cases:
            with self.subTest(attrs=attrs):
                self.client_obj.documents.all().delete()
                doc = create_test_document(self.client_obj, doc_type=DocumentType.PASSPORT.value, expiry_date=attrs.get("expiry_date"))
                if attrs.get("rejection_reason"):
                    doc.rejection_reason = attrs["rejection_reason"]
                    doc.save(update_fields=["rejection_reason"])
                if attrs.get("delete_file"):
                    default_storage.delete(doc.file.name)
                if attrs.get("archive"):
                    doc.archive()
                self.assertFalse(self._transition_allowed())

    def test_valid_document_allows_submission_transition(self):
        create_test_document(self.client_obj, doc_type=DocumentType.PASSPORT.value)
        self.assertTrue(self._transition_allowed())


class OnboardingTransitionConsistencyTests(TestCase):
    def test_successful_transition_updates_mos_and_client(self):
        client = create_test_client(workflow_stage="document_collection", purpose="other")
        purpose = client.get_document_requirement_purpose()
        DocumentRequirement.objects.filter(application_purpose=purpose).delete()
        DocumentRequirement.objects.create(application_purpose=purpose, document_type=DocumentType.PASSPORT.value, is_required=True)
        create_test_document(client, doc_type=DocumentType.PASSPORT.value)
        mos = MOSApplicationData.objects.update_or_create(client=client, defaults={"status": "mos_package_ready"})[0]
        transition_client_workflow(client=client, target_stage="application_submitted")
        mos.status = "submitted_in_mos"
        mos.save(update_fields=["status"])
        client.refresh_from_db()
        mos.refresh_from_db()
        self.assertEqual(client.workflow_stage, "application_submitted")
        self.assertEqual(mos.status, "submitted_in_mos")

    def test_forbidden_transition_changes_neither_model(self):
        client = create_test_client(workflow_stage="document_collection", purpose="other")
        purpose = client.get_document_requirement_purpose()
        DocumentRequirement.objects.filter(application_purpose=purpose).delete()
        DocumentRequirement.objects.create(application_purpose=purpose, document_type=DocumentType.PASSPORT.value, is_required=True)
        mos = MOSApplicationData.objects.update_or_create(client=client, defaults={"status": "mos_package_ready"})[0]
        with self.assertRaises(ValidationError):
            transition_client_workflow(client=client, target_stage="application_submitted")
        client.refresh_from_db()
        mos.refresh_from_db()
        self.assertEqual(client.workflow_stage, "document_collection")
        self.assertEqual(mos.status, "mos_package_ready")

    def test_atomic_error_rolls_back_partial_data(self):
        client = create_test_client(workflow_stage="document_collection", purpose="other")
        purpose = client.get_document_requirement_purpose()
        DocumentRequirement.objects.filter(application_purpose=purpose).delete()
        DocumentRequirement.objects.create(application_purpose=purpose, document_type=DocumentType.PASSPORT.value, is_required=True)
        create_test_document(client, doc_type=DocumentType.PASSPORT.value)
        mos = MOSApplicationData.objects.update_or_create(client=client, defaults={"status": "mos_package_ready"})[0]
        with patch("clients.services.workflow_transitions.log_client_activity", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                from django.db import transaction
                with transaction.atomic():
                    transition_client_workflow(client=client, target_stage="application_submitted")
                    mos.status = "submitted_in_mos"
        mos.save(update_fields=["status"])
        client.refresh_from_db()
        mos.refresh_from_db()
        self.assertEqual(client.workflow_stage, "document_collection")
        self.assertEqual(mos.status, "mos_package_ready")


class PaymentTimelineTests(TestCase):
    def test_pending_and_partial_payment_show_payment_step(self):
        for status, amount in [("pending", Decimal("0.00")), ("partial", Decimal("50.00"))]:
            client = create_test_client()
            MOSApplicationData.objects.update_or_create(client=client, defaults={"status": "approved_by_staff"})
            client.refresh_from_db()
            Payment.objects.create(client=client, service_description="work_service", total_amount=Decimal("100.00"), amount_paid=amount, status=status)
            self.assertEqual(client.get_case_step(), 5)

    def test_paid_refunded_and_no_payments_do_not_show_payment_step(self):
        for status in ["paid", "refunded", None]:
            client = create_test_client()
            MOSApplicationData.objects.update_or_create(client=client, defaults={"status": "approved_by_staff"})
            client.refresh_from_db()
            if status:
                Payment.objects.create(client=client, service_description="work_service", total_amount=Decimal("100.00"), amount_paid=Decimal("100.00"), status=status)
            self.assertEqual(client.get_case_step(), 6)
