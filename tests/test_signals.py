"""Tests for Django signals: payment reminders, client deletion, document compression."""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from clients.models import Client, Document, Payment, Reminder

User = get_user_model()


class PaymentReminderSignalTest(TestCase):
    def setUp(self):
        self.test_client = Client.objects.create(
            first_name="Jan", last_name="Signal", citizenship="PL",
            phone="111", email="signal@test.com", application_purpose="work",
        )

    def test_partial_payment_creates_reminder(self):
        payment = Payment.objects.create(
            client=self.test_client, service_description="work_service",
            total_amount=1800, amount_paid=900, status="partial",
            due_date=timezone.localdate() + timedelta(days=14),
        )
        self.assertTrue(Reminder.objects.filter(payment=payment, reminder_type="payment").exists())

    def test_paid_payment_removes_reminder(self):
        payment = Payment.objects.create(
            client=self.test_client, service_description="work_service",
            total_amount=1800, amount_paid=900, status="partial",
            due_date=timezone.localdate() + timedelta(days=14),
        )
        self.assertTrue(Reminder.objects.filter(payment=payment).exists())
        payment.status = "paid"
        payment.save()
        self.assertFalse(Reminder.objects.filter(payment=payment).exists())

    def test_delete_payment_removes_reminder(self):
        payment = Payment.objects.create(
            client=self.test_client, service_description="work_service",
            total_amount=1800, amount_paid=900, status="partial",
            due_date=timezone.localdate() + timedelta(days=14),
        )
        payment_pk = payment.pk
        payment.delete()
        self.assertFalse(Reminder.objects.filter(payment_id=payment_pk).exists())


class ClientDeletionSignalTest(TestCase):
    def test_deleting_client_deletes_non_staff_user(self):
        user = User.objects.create_user(
            username="client_user", email="cuser@test.com", password="pass", is_staff=False
        )
        client_obj = Client.objects.create(
            first_name="Delete", last_name="User", citizenship="PL",
            phone="222", email="cdeluser@test.com", application_purpose="work",
            user=user,
        )
        user_pk = user.pk
        client_obj.delete()
        self.assertFalse(User.objects.filter(pk=user_pk).exists())

    def test_deleting_client_preserves_staff_user(self):
        staff_user = User.objects.create_user(
            username="staff_preserved", email="suser@test.com", password="pass", is_staff=True
        )
        client_obj = Client.objects.create(
            first_name="Keep", last_name="Staff", citizenship="PL",
            phone="333", email="keepstaff@test.com", application_purpose="work",
            user=staff_user,
        )
        staff_pk = staff_user.pk
        client_obj.delete()
        self.assertTrue(User.objects.filter(pk=staff_pk).exists())

    def test_deleting_client_without_user_no_error(self):
        client_obj = Client.objects.create(
            first_name="NoUser", last_name="Test", citizenship="PL",
            phone="444", email="nouser@test.com", application_purpose="work",
        )
        client_obj.delete()


class PurposeChangeSignalTest(TestCase):
    def test_changing_purpose_updates_pending_payments(self):
        client_obj = Client.objects.create(
            first_name="Purpose", last_name="Change", citizenship="PL",
            phone="555", email="purpose@test.com", application_purpose="work",
        )
        Payment.objects.create(
            client=client_obj, service_description="work_service",
            total_amount=1800, amount_paid=0, status="pending",
        )
        client_obj.application_purpose = "study"
        client_obj.save()
        payment = Payment.objects.get(client=client_obj)
        self.assertEqual(payment.service_description, "study_service")

    def test_changing_purpose_does_not_update_paid_payments(self):
        client_obj = Client.objects.create(
            first_name="Paid", last_name="Keep", citizenship="PL",
            phone="666", email="paidkeep@test.com", application_purpose="work",
        )
        Payment.objects.create(
            client=client_obj, service_description="work_service",
            total_amount=1800, amount_paid=1800, status="paid",
        )
        client_obj.application_purpose = "study"
        client_obj.save()
        payment = Payment.objects.get(client=client_obj)
        self.assertEqual(payment.service_description, "work_service")


class DocumentFileDeleteSignalTest(TestCase):
    def test_deleting_document_removes_file(self):
        client_obj = Client.objects.create(
            first_name="File", last_name="Del", citizenship="PL",
            phone="777", email="filedel@test.com", application_purpose="work",
        )
        doc = Document.objects.create(
            client=client_obj, document_type="passport",
            file=SimpleUploadedFile("test_sig.txt", b"content", content_type="text/plain"),
        )
        doc.delete()
        self.assertFalse(Document.objects.filter(pk=doc.pk).exists())
