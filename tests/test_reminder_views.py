"""Tests for reminder views: list, action, update, send_document_reminder."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, Client as DjangoClient
from django.urls import reverse
from django.utils import timezone

from clients.models import Client, Document, Reminder

User = get_user_model()


class ReminderViewsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create_user(
            username="staff", email="staff@test.com", password="testpass123", is_staff=True
        )

    def setUp(self):
        self.client = DjangoClient()
        self.client.login(username="staff", password="testpass123")
        self.test_client = Client.objects.create(
            first_name="Jan", last_name="Kowalski", citizenship="Poland",
            phone="123456789", email="jan_rem@test.com", application_purpose="work",
        )

    def test_document_reminder_list_renders(self):
        url = reverse("clients:document_reminder_list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_payment_reminder_list_renders(self):
        url = reverse("clients:payment_reminder_list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_reminder_action_deactivate(self):
        reminder = Reminder.objects.create(
            client=self.test_client, reminder_type="document",
            title="Test reminder", due_date=timezone.localdate() + timedelta(days=5),
            is_active=True,
        )
        url = reverse("clients:reminder_action", kwargs={"reminder_id": reminder.pk})
        resp = self.client.post(url, {"action": "deactivate"})
        self.assertEqual(resp.status_code, 302)
        reminder.refresh_from_db()
        self.assertFalse(reminder.is_active)

    def test_reminder_action_delete(self):
        reminder = Reminder.objects.create(
            client=self.test_client, reminder_type="document",
            title="Test reminder", due_date=timezone.localdate() + timedelta(days=5),
            is_active=True,
        )
        url = reverse("clients:reminder_action", kwargs={"reminder_id": reminder.pk})
        resp = self.client.post(url, {"action": "delete"})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Reminder.objects.filter(pk=reminder.pk).exists())

    def test_run_update_reminders_post(self):
        url = reverse("clients:run_update_reminders")
        resp = self.client.post(url, {"next": "documents"})
        self.assertIn(resp.status_code, (302,))

    def test_run_update_reminders_get_redirects(self):
        url = reverse("clients:run_update_reminders")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_document_reminder_list_filters(self):
        url = reverse("clients:document_reminder_list")
        resp = self.client.get(url, {
            "doc_client": str(self.test_client.pk),
            "doc_start_date": "2025-01-01",
            "doc_end_date": "2027-12-31",
        })
        self.assertEqual(resp.status_code, 200)

    def test_send_document_reminder_email_no_docs(self):
        url = reverse("clients:send_document_reminder_email", kwargs={"client_id": self.test_client.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
