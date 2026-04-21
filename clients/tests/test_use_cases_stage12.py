from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from clients.models import Client, ClientActivity, Document, Payment, Reminder
from clients.use_cases.payments import (
    create_payment_for_client,
    delete_payment_for_client,
    update_payment_for_client,
)
from clients.use_cases.reminders import (
    deactivate_reminder,
    delete_reminder,
    send_document_reminder_for_client,
    send_document_reminder_for_reminder,
)


class UseCasesStage12Tests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            email="staff-stage12@example.com",
            password="pass",
            is_staff=True,
        )
        self.client_obj = Client.objects.create(
            first_name="Olena",
            last_name="Bondar",
            citizenship="UA",
            phone="+48111111111",
            email="olena-stage12@example.com",
            legal_basis_end_date=timezone.localdate() + timedelta(days=14),
        )

    def test_create_payment_use_case_creates_payment_and_activity(self):
        result = create_payment_for_client(
            client=self.client_obj,
            actor=self.staff,
            cleaned_data={
                "service_description": "consultation",
                "total_amount": Decimal("250.00"),
                "amount_paid": Decimal("50.00"),
                "status": "partial",
                "payment_method": "card",
                "payment_date": None,
                "due_date": timezone.localdate() + timedelta(days=5),
                "transaction_id": "txn-123",
            },
        )

        payment = result.payment
        self.assertIsNotNone(payment)
        self.assertEqual(payment.client, self.client_obj)
        self.assertEqual(payment.total_amount, Decimal("250.00"))
        self.assertEqual(payment.amount_paid, Decimal("50.00"))
        activity = ClientActivity.objects.get(client=self.client_obj, event_type="payment_created")
        self.assertEqual(activity.actor, self.staff)
        self.assertEqual(activity.payment, payment)
        self.assertEqual(activity.metadata["payment_id"], payment.pk)

    def test_update_payment_use_case_logs_changed_fields(self):
        payment = Payment.objects.create(
            client=self.client_obj,
            service_description="consultation",
            total_amount=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
            status="pending",
        )

        result = update_payment_for_client(
            payment=payment,
            actor=self.staff,
            cleaned_data={
                "service_description": "consultation",
                "total_amount": Decimal("120.00"),
                "amount_paid": Decimal("20.00"),
                "status": "partial",
                "payment_method": "transfer",
                "payment_date": None,
                "due_date": None,
                "transaction_id": "txn-456",
            },
        )

        payment.refresh_from_db()
        self.assertEqual(
            result.changed_fields,
            ("total_amount", "amount_paid", "status", "payment_method", "transaction_id"),
        )
        self.assertEqual(payment.total_amount, Decimal("120.00"))
        activity = ClientActivity.objects.get(client=self.client_obj, event_type="payment_updated")
        self.assertEqual(activity.payment, payment)
        self.assertEqual(activity.metadata["changed_fields"], list(result.changed_fields))

    def test_update_payment_use_case_skips_activity_when_nothing_changed(self):
        payment = Payment.objects.create(
            client=self.client_obj,
            service_description="consultation",
            total_amount=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
            status="pending",
            payment_method="card",
        )

        result = update_payment_for_client(
            payment=payment,
            actor=self.staff,
            cleaned_data={
                "service_description": "consultation",
                "total_amount": Decimal("100.00"),
                "amount_paid": Decimal("0.00"),
                "status": "pending",
                "payment_method": "card",
                "payment_date": None,
                "due_date": None,
                "transaction_id": None,
            },
        )

        self.assertEqual(result.changed_fields, ())
        self.assertFalse(
            ClientActivity.objects.filter(client=self.client_obj, event_type="payment_updated").exists()
        )

    def test_delete_payment_use_case_deletes_payment_and_keeps_audit_metadata(self):
        payment = Payment.objects.create(
            client=self.client_obj,
            service_description="study_service",
            total_amount=Decimal("300.00"),
            amount_paid=Decimal("0.00"),
            status="pending",
        )

        result = delete_payment_for_client(payment=payment, actor=self.staff)

        self.assertEqual(result.deleted_payment_id, payment.pk)
        self.assertFalse(Payment.objects.filter(pk=payment.pk).exists())
        activity = ClientActivity.objects.get(client=self.client_obj, event_type="payment_deleted")
        self.assertEqual(activity.metadata["payment_id"], payment.pk)
        self.assertIsNone(activity.payment)

    def test_deactivate_reminder_use_case_marks_inactive_and_logs_activity(self):
        reminder = Reminder.objects.create(
            client=self.client_obj,
            reminder_type="document",
            title="Renew passport",
            due_date=timezone.localdate() + timedelta(days=3),
            is_active=True,
        )

        result = deactivate_reminder(reminder=reminder, actor=self.staff)

        reminder.refresh_from_db()
        self.assertEqual(result.reminder, reminder)
        self.assertFalse(reminder.is_active)
        activity = ClientActivity.objects.get(client=self.client_obj, event_type="reminder_deactivated")
        self.assertEqual(activity.metadata["reminder_id"], reminder.pk)

    def test_delete_reminder_use_case_deletes_record_and_logs_activity(self):
        reminder = Reminder.objects.create(
            client=self.client_obj,
            reminder_type="payment",
            title="Payment due",
            due_date=timezone.localdate() + timedelta(days=2),
            is_active=True,
        )

        result = delete_reminder(reminder=reminder, actor=self.staff)

        self.assertEqual(result.deleted_reminder_id, reminder.pk)
        self.assertFalse(Reminder.objects.filter(pk=reminder.pk).exists())
        activity = ClientActivity.objects.get(client=self.client_obj, event_type="reminder_deleted")
        self.assertEqual(activity.metadata["reminder_id"], reminder.pk)

    def test_send_document_reminder_for_single_reminder_passes_actor_and_document(self):
        document = Document.objects.create(
            client=self.client_obj,
            document_type="passport",
            file="documents/passport.pdf",
            expiry_date=timezone.localdate() + timedelta(days=10),
        )
        reminder = Reminder.objects.create(
            client=self.client_obj,
            document=document,
            reminder_type="document",
            title="Passport expires soon",
            due_date=timezone.localdate() + timedelta(days=5),
            is_active=True,
        )
        send_email = Mock(return_value=1)

        result = send_document_reminder_for_reminder(
            reminder=reminder,
            actor=self.staff,
            send_email=send_email,
        )

        self.assertTrue(result.email_sent)
        self.assertEqual(result.affected_documents_count, 1)
        send_email.assert_called_once_with(self.client_obj, [document], sent_by=self.staff)

    def test_send_document_reminder_for_client_uses_only_active_documents_with_expiry(self):
        valid_document = Document.objects.create(
            client=self.client_obj,
            document_type="passport",
            file="documents/passport-valid.pdf",
            expiry_date=timezone.localdate() + timedelta(days=8),
        )
        missing_expiry_document = Document.objects.create(
            client=self.client_obj,
            document_type="insurance",
            file="documents/insurance.pdf",
            expiry_date=None,
        )
        inactive_document = Document.objects.create(
            client=self.client_obj,
            document_type="work_permit",
            file="documents/work-permit.pdf",
            expiry_date=timezone.localdate() + timedelta(days=15),
        )
        Reminder.objects.create(
            client=self.client_obj,
            document=valid_document,
            reminder_type="document",
            title="Valid reminder",
            due_date=timezone.localdate() + timedelta(days=5),
            is_active=True,
        )
        Reminder.objects.create(
            client=self.client_obj,
            document=missing_expiry_document,
            reminder_type="document",
            title="No expiry date",
            due_date=timezone.localdate() + timedelta(days=5),
            is_active=True,
        )
        Reminder.objects.create(
            client=self.client_obj,
            document=inactive_document,
            reminder_type="document",
            title="Inactive reminder",
            due_date=timezone.localdate() + timedelta(days=5),
            is_active=False,
        )
        send_email = Mock(return_value=1)

        result = send_document_reminder_for_client(
            client=self.client_obj,
            actor=self.staff,
            send_email=send_email,
        )

        self.assertTrue(result.email_sent)
        self.assertEqual(result.affected_documents_count, 1)
        send_email.assert_called_once_with(self.client_obj, [valid_document], sent_by=self.staff)
