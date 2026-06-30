from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from clients.models import Case, Document, Payment, Reminder, StaffTask
from clients.services.access import (
    accessible_documents_queryset,
    accessible_payments_queryset,
    accessible_reminders_queryset,
    accessible_tasks_queryset,
)
from clients.services.archive import archive_case, restore_case
from clients.testing.factories import create_test_client, create_test_document, create_test_user


class ActiveCaseArchiveVisibilityTests(TestCase):
    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client()
        self.case = self.client_obj.cases.get()
        self.document = create_test_document(self.client_obj, case=self.case)
        self.payment = Payment.objects.create(
            client=self.client_obj,
            case=self.case,
            service_description="work_service",
            total_amount=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
            status="pending",
        )
        self.task = StaffTask.objects.create(
            client=self.client_obj,
            case=self.case,
            title="Archive visibility task",
            description="Task for active list filtering",
            due_date=timezone.localdate(),
            created_by=self.staff,
        )
        self.reminder = Reminder.objects.create(
            client=self.client_obj,
            case=self.case,
            reminder_type="other",
            title="Archive visibility reminder",
            due_date=timezone.localdate(),
            is_active=True,
        )

    def test_staff_archive_hides_case_children_from_active_querysets_and_restore_returns_them(self) -> None:
        batch = archive_case(self.case, self.staff)

        self.assertFalse(Case.objects.filter(pk=self.case.pk).exists())
        self.assertFalse(accessible_documents_queryset(self.staff, Document.objects.all()).filter(pk=self.document.pk).exists())
        self.assertFalse(accessible_payments_queryset(self.staff, Payment.objects.all()).filter(pk=self.payment.pk).exists())
        self.assertFalse(accessible_tasks_queryset(self.staff, StaffTask.objects.all()).filter(pk=self.task.pk).exists())
        self.assertFalse(accessible_reminders_queryset(self.staff, Reminder.objects.all()).filter(pk=self.reminder.pk).exists())

        self.assertTrue(Document.all_objects.filter(pk=self.document.pk).exists())
        self.assertTrue(Payment.all_objects.filter(pk=self.payment.pk).exists())
        self.assertTrue(StaffTask.objects.filter(pk=self.task.pk).exists())
        self.assertTrue(Reminder.objects.filter(pk=self.reminder.pk).exists())
        self.assertTrue(
            accessible_documents_queryset(
                self.staff,
                Document.all_objects.all(),
                include_archived_cases=True,
            ).filter(pk=self.document.pk).exists()
        )
        self.assertTrue(
            accessible_payments_queryset(
                self.staff,
                Payment.all_objects.all(),
                include_archived_cases=True,
            ).filter(pk=self.payment.pk).exists()
        )
        self.assertTrue(
            accessible_tasks_queryset(
                self.staff,
                StaffTask.objects.all(),
                include_archived_cases=True,
            ).filter(pk=self.task.pk).exists()
        )
        self.assertTrue(
            accessible_reminders_queryset(
                self.staff,
                Reminder.objects.all(),
                include_archived_cases=True,
            ).filter(pk=self.reminder.pk).exists()
        )

        restore_case(Case.all_objects.get(pk=self.case.pk), self.staff, batch)

        self.assertTrue(Case.objects.filter(pk=self.case.pk).exists())
        self.assertTrue(accessible_documents_queryset(self.staff, Document.objects.all()).filter(pk=self.document.pk).exists())
        self.assertTrue(accessible_payments_queryset(self.staff, Payment.objects.all()).filter(pk=self.payment.pk).exists())
        self.assertTrue(accessible_tasks_queryset(self.staff, StaffTask.objects.all()).filter(pk=self.task.pk).exists())
        self.assertTrue(accessible_reminders_queryset(self.staff, Reminder.objects.all()).filter(pk=self.reminder.pk).exists())


class ClientCaseIntegrityTests(TestCase):
    def setUp(self) -> None:
        self.client_a = create_test_client(first_name="A")
        self.client_b = create_test_client(first_name="B")
        self.case_a = self.client_a.cases.get()
        self.case_b = self.client_b.cases.get()

    def test_normal_creation_uses_matching_client_and_case(self) -> None:
        document = create_test_document(self.client_a, case=self.case_a)
        self.assertEqual(document.client_id, self.client_a.pk)
        self.assertEqual(document.case.client_id, self.client_a.pk)

    def test_mismatched_client_case_rejected_on_create(self) -> None:
        with self.assertRaises(ValidationError):
            create_test_document(self.client_a, case=self.case_b)

    def test_mismatched_case_edit_rejected(self) -> None:
        document = create_test_document(self.client_a, case=self.case_a)
        document.case = self.case_b
        with self.assertRaises(ValidationError):
            document.save(update_fields=["case"])

    def test_mismatched_client_edit_rejected(self) -> None:
        document = create_test_document(self.client_a, case=self.case_a)
        document.client = self.client_b
        with self.assertRaises(ValidationError):
            document.save(update_fields=["client"])
