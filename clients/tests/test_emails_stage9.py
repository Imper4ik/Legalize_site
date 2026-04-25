from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from clients.models import Client, Company, EmailCampaign, EmailLog
from clients.services.responses import NO_STORE_HEADER
from clients.services.roles import ensure_predefined_roles


class EmailViewsStage9Tests(TestCase):
    def setUp(self):
        ensure_predefined_roles()
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(email="staff_email@example.com", password="pass", is_staff=True)
        self.staff.groups.add(Group.objects.get(name="Manager"))
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
        self.assertEqual(response["Cache-Control"], NO_STORE_HEADER)
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
    def test_send_custom_email_is_idempotent_for_same_payload(self, send_mail_mock):
        url = reverse("clients:send_custom_email", kwargs={"pk": self.client_obj.pk})

        first = self.client.post(url, data={"subject": "Hello", "body": "Test body"})
        second = self.client.post(url, data={"subject": "Hello", "body": "Test body"})

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(send_mail_mock.call_count, 1)
        self.assertEqual(EmailLog.objects.filter(template_type="custom").count(), 1)

    @patch("clients.views.emails.send_mail", return_value=1)
    def test_send_custom_email_requires_subject_and_body(self, send_mail_mock):
        response = self.client.post(
            reverse("clients:send_custom_email", kwargs={"pk": self.client_obj.pk}),
            data={"subject": "", "body": ""},
        )

        self.assertEqual(response.status_code, 302)
        send_mail_mock.assert_not_called()

    @patch("clients.views.emails._log_email")
    @patch("clients.views.emails._send_confirmation_email")
    @patch("clients.views.emails.send_mail", return_value=1)
    def test_mass_email_view_queues_campaign_for_worker(self, send_mail_mock, confirm_mock, log_mock):
        company = Company.objects.create(name="Mass Co")
        Client.objects.create(
            first_name="Mass",
            last_name="Target",
            citizenship="PL",
            phone="+48999111222",
            email="mass-target@example.com",
            company=company,
        )

        response = self.client.post(
            reverse("clients:mass_email"),
            data={"subject": "News", "message": "Body", "company": company.pk},
        )

        self.assertEqual(response.status_code, 302)
        campaign = EmailCampaign.objects.get()
        self.assertEqual(campaign.status, EmailCampaign.STATUS_PENDING)
        self.assertEqual(campaign.total_recipients, 1)
        self.assertEqual(campaign.recipient_emails_list, ["mass-target@example.com"])
        self.assertEqual(campaign.filters_snapshot["company_id"], company.pk)
        self.assertEqual(campaign.created_by, self.staff)
        send_mail_mock.assert_not_called()
        confirm_mock.assert_not_called()
        log_mock.assert_not_called()

    @patch("clients.services.email_campaigns._log_email")
    @patch("clients.services.email_campaigns._send_confirmation_email")
    @patch("clients.services.email_campaigns.send_mail", return_value=1)
    def test_process_email_campaigns_command_sends_pending_campaign(self, send_mail_mock, confirm_mock, log_mock):
        campaign = EmailCampaign.objects.create(
            subject="News",
            message="Body",
            total_recipients=1,
            recipient_emails=["email-user@example.com"],
            created_by=self.staff,
        )

        call_command("process_email_campaigns", campaign_id=campaign.pk)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, EmailCampaign.STATUS_COMPLETED)
        self.assertEqual(campaign.sent_count, 1)
        self.assertEqual(campaign.failed_count, 0)
        self.assertIsNotNone(campaign.started_at)
        self.assertIsNotNone(campaign.completed_at)
        send_mail_mock.assert_called_once()
        confirm_mock.assert_called_once()
        log_mock.assert_called_once()
        self.assertEqual(log_mock.call_args.kwargs["sent_by"], self.staff)

    @patch("clients.services.email_campaigns.send_mail", return_value=1)
    def test_process_campaign_is_idempotent_per_recipient(self, send_mail_mock):
        campaign = EmailCampaign.objects.create(
            subject="News",
            message="Body",
            total_recipients=1,
            recipient_emails=["email-user@example.com"],
            created_by=self.staff,
        )

        call_command("process_email_campaigns", campaign_id=campaign.pk)
        self.assertEqual(send_mail_mock.call_count, 1)

        # Direct retry after completion should not process again.
        call_command("process_email_campaigns", campaign_id=campaign.pk)
        self.assertEqual(send_mail_mock.call_count, 1)
        self.assertEqual(EmailLog.objects.filter(template_type="mass_email").count(), 1)

    def test_campaign_status_api_returns_no_store_payload(self):
        campaign = EmailCampaign.objects.create(
            subject="Queued",
            message="Body",
            total_recipients=1,
            recipient_emails=["email-user@example.com"],
            filters_snapshot={"status": "new"},
            created_by=self.staff,
        )

        response = self.client.get(reverse("clients:campaign_status_api", kwargs={"campaign_id": campaign.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], NO_STORE_HEADER)
        payload = response.json()
        self.assertEqual(payload["status"], EmailCampaign.STATUS_PENDING)
        self.assertEqual(payload["filters_snapshot"]["status"], "new")
        self.assertEqual(payload["created_by"], self.staff.email)

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
