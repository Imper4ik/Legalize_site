"""Tests for email-related views: send_custom_email, email_preview_api, mass_email_view."""
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, Client as DjangoClient
from django.urls import reverse

from clients.models import Client

User = get_user_model()


class EmailViewsBaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create_user(
            username="staff", email="staff@test.com", password="testpass123", is_staff=True
        )

    def setUp(self):
        self.client = DjangoClient()
        self.client.login(username="staff", password="testpass123")
        self.test_client = Client.objects.create(
            first_name="Jan",
            last_name="Kowalski",
            citizenship="Poland",
            phone="123456789",
            email="jan@test.com",
            application_purpose="work",
        )


class SendCustomEmailTest(EmailViewsBaseTest):
    def test_send_email_success(self):
        url = reverse("clients:send_custom_email", kwargs={"pk": self.test_client.pk})
        resp = self.client.post(url, {"subject": "Test Subject", "body": "Test body text"})
        self.assertEqual(resp.status_code, 302)
        # locmem backend captures sent emails
        self.assertTrue(len(mail.outbox) >= 1)
        self.assertEqual(mail.outbox[0].subject, "Test Subject")

    def test_send_email_missing_subject(self):
        url = reverse("clients:send_custom_email", kwargs={"pk": self.test_client.pk})
        resp = self.client.post(url, {"subject": "", "body": "Body"})
        self.assertEqual(resp.status_code, 302)
        # No email should be sent
        self.assertEqual(len(mail.outbox), 0)

    def test_send_email_no_client_email(self):
        self.test_client.email = ""
        self.test_client.save()
        url = reverse("clients:send_custom_email", kwargs={"pk": self.test_client.pk})
        resp = self.client.post(url, {"subject": "Sub", "body": "Body"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)


class EmailPreviewApiTest(EmailViewsBaseTest):
    def test_custom_template_returns_empty(self):
        url = reverse("clients:email_preview_api", kwargs={"pk": self.test_client.pk})
        resp = self.client.get(url, {"template_type": "custom"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["subject"], "")
        self.assertEqual(data["body"], "")

    def test_no_template_type_returns_empty(self):
        url = reverse("clients:email_preview_api", kwargs={"pk": self.test_client.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["subject"], "")


class MassEmailViewTest(EmailViewsBaseTest):
    def test_get_renders_form(self):
        url = reverse("clients:mass_email")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "form")

    def test_post_sends_emails(self):
        # Create a second client with email
        Client.objects.create(
            first_name="Anna", last_name="Nowak", citizenship="Poland",
            phone="987654321", email="anna@test.com", application_purpose="study",
        )
        url = reverse("clients:mass_email")
        resp = self.client.post(url, {"subject": "Mass Subject", "message": "Mass body"})
        self.assertEqual(resp.status_code, 302)
        # At least 2 emails should be sent (jan + anna)
        self.assertGreaterEqual(len(mail.outbox), 2)
