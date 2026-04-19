from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from clients.models import Client


class EmailViewsStage9Tests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(email="staff_email@example.com", password="pass", is_staff=True)
        self.client.login(email="staff_email@example.com", password="pass")

        self.client_obj = Client.objects.create(
            first_name="Email",
            last_name="User",
            citizenship="PL",
            phone="+48111222333",
            email="email-user@example.com",
        )

    def test_email_preview_returns_insufficient_data_message_for_missing_template_context(self):
        response = self.client.get(
            reverse("clients:email_preview_api", kwargs={"pk": self.client_obj.pk}),
            {"template_type": "appointment_notification"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("subject", payload)
        self.assertIn("body", payload)
        self.assertIn("Недостаточно данных", payload["body"])

    @patch("clients.views.emails._log_email")
    @patch("clients.views.emails._send_confirmation_email")
    @patch("clients.views.emails.send_mail", return_value=1)
    def test_send_custom_email_success_path(self, send_mail_mock, confirm_mock, log_mock):
        response = self.client.post(
            reverse("clients:send_custom_email", kwargs={"pk": self.client_obj.pk}),
            data={"subject": "Hello", "body": "Test body"},
        )

        self.assertEqual(response.status_code, 302)
        send_mail_mock.assert_called_once()
        confirm_mock.assert_called_once()
        log_mock.assert_called_once()

    @patch("clients.views.emails.send_mail", return_value=1)
    def test_send_custom_email_requires_subject_and_body(self, send_mail_mock):
        response = self.client.post(
            reverse("clients:send_custom_email", kwargs={"pk": self.client_obj.pk}),
            data={"subject": "", "body": ""},
        )

        self.assertEqual(response.status_code, 302)
        send_mail_mock.assert_not_called()

    @patch("clients.views.emails.send_mail", return_value=1)
    @patch("clients.views.emails._send_confirmation_email")
    @patch("clients.views.emails._log_email")
    @patch("clients.views.emails.threading.Thread.start", autospec=True)
    def test_mass_email_view_sends_to_matching_clients(self, mock_thread_start, log_mock, confirm_mock, send_mail_mock):
        def fake_start(thread_instance):
            thread_instance._target(*thread_instance._args, **thread_instance._kwargs)
        mock_thread_start.side_effect = fake_start
        other = Client.objects.create(
            first_name="Mass",
            last_name="Target",
            citizenship="PL",
            phone="+48999111222",
            email="mass-target@example.com",
            status="new",
        )

        response = self.client.post(
            reverse("clients:mass_email"),
            data={"subject": "News", "message": "Body", "status": "new"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertGreaterEqual(send_mail_mock.call_count, 1)
        confirm_mock.assert_called_once()
        self.assertGreaterEqual(log_mock.call_count, 1)

    @patch("clients.views.emails.send_mail", return_value=1)
    def test_send_custom_email_handles_client_without_email(self, send_mail_mock):
        self.client_obj.email = ""
        self.client_obj.save(update_fields=["email"])

        response = self.client.post(
            reverse("clients:send_custom_email", kwargs={"pk": self.client_obj.pk}),
            data={"subject": "Hello", "body": "Body"},
        )

        self.assertEqual(response.status_code, 302)
        send_mail_mock.assert_not_called()
