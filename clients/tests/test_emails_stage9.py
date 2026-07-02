from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from clients.models import Client, Company, EmailCampaign, EmailLog
from clients.services.notifications import _send_email, build_email_idempotency_key
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
        expected_body = _(
            "Недостаточно данных у клиента для этого шаблона "
            "(например, нет даты отпечатков или списка документов)."
        )
        self.assertIn(expected_body, payload["body"])

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
        self.assertEqual(EmailLog.objects.get(template_type="custom").delivery_status, EmailLog.DELIVERY_STATUS_SENT)

    @patch("clients.views.emails.send_mail", return_value=1)
    def test_send_custom_email_skips_existing_queued_idempotency_key(self, send_mail_mock):
        key = build_email_idempotency_key(
            "custom_email",
            self.staff.pk,
            self.client_obj.pk,
            self.client_obj.email,
            "Hello",
            "Test body",
        )
        EmailLog.objects.create(
            client=self.client_obj,
            subject="Hello",
            body="Test body",
            recipients=self.client_obj.email,
            template_type="custom",
            sent_by=self.staff,
            idempotency_key=key,
            delivery_status=EmailLog.DELIVERY_STATUS_QUEUED,
        )

        response = self.client.post(
            reverse("clients:send_custom_email", kwargs={"pk": self.client_obj.pk}),
            data={"subject": "Hello", "body": "Test body"},
        )

        self.assertEqual(response.status_code, 302)
        send_mail_mock.assert_not_called()
        self.assertEqual(EmailLog.objects.filter(idempotency_key=key).count(), 1)

    @patch("clients.views.emails._send_confirmation_email", side_effect=RuntimeError("copy failed"))
    @patch("clients.views.emails.send_mail", return_value=1)
    def test_send_custom_email_stays_sent_when_confirmation_copy_fails(self, send_mail_mock, confirm_mock):
        response = self.client.post(
            reverse("clients:send_custom_email", kwargs={"pk": self.client_obj.pk}),
            data={"subject": "Hello", "body": "Test body"},
        )

        self.assertEqual(response.status_code, 302)
        send_mail_mock.assert_called_once()
        confirm_mock.assert_called_once()
        email_log = EmailLog.objects.get(template_type="custom")
        self.assertEqual(email_log.delivery_status, EmailLog.DELIVERY_STATUS_SENT)

    @patch("clients.services.notifications._send_confirmation_email")
    @patch("clients.services.notifications.send_mail")
    def test_send_email_reserves_idempotency_before_smtp_io(self, send_mail_mock, confirm_mock):
        key = build_email_idempotency_key("service-email", self.client_obj.pk)

        def fake_send_mail(*_args, **_kwargs):
            queued_log = EmailLog.objects.get(idempotency_key=key)
            self.assertEqual(queued_log.delivery_status, EmailLog.DELIVERY_STATUS_QUEUED)
            return 1

        send_mail_mock.side_effect = fake_send_mail

        sent_count = _send_email(
            "Service message",
            "Body",
            [self.client_obj.email],
            client=self.client_obj,
            template_type="service",
            sent_by=self.staff,
            idempotency_key=key,
        )

        self.assertEqual(sent_count, 1)
        confirm_mock.assert_called_once()
        email_log = EmailLog.objects.get(idempotency_key=key)
        self.assertEqual(email_log.delivery_status, EmailLog.DELIVERY_STATUS_SENT)

    @patch("clients.services.notifications._send_confirmation_email", side_effect=RuntimeError("copy failed"))
    @patch("clients.services.notifications.send_mail", return_value=1)
    def test_send_email_stays_sent_when_confirmation_copy_fails(self, send_mail_mock, confirm_mock):
        key = build_email_idempotency_key("service-email-copy-failure", self.client_obj.pk)

        sent_count = _send_email(
            "Service message",
            "Body",
            [self.client_obj.email],
            client=self.client_obj,
            template_type="service",
            sent_by=self.staff,
            idempotency_key=key,
        )

        self.assertEqual(sent_count, 1)
        send_mail_mock.assert_called_once()
        confirm_mock.assert_called_once()
        email_log = EmailLog.objects.get(idempotency_key=key)
        self.assertEqual(email_log.delivery_status, EmailLog.DELIVERY_STATUS_SENT)

    @patch("clients.services.notifications._send_confirmation_email")
    @patch("clients.services.notifications.send_mail", return_value=1)
    def test_onboarding_completed_email_is_logged_as_sent(self, send_mail_mock, confirm_mock):
        # Regression: the "skip staff confirmation copy" special case must not
        # route a successful onboarding_completed send into the failed branch.
        key = build_email_idempotency_key("onboarding-completed-log", self.client_obj.pk)

        sent_count = _send_email(
            "Client completed onboarding",
            "Body",
            ["office@example.com"],
            client=self.client_obj,
            template_type="onboarding_completed",
            sent_by=self.staff,
            idempotency_key=key,
        )

        self.assertEqual(sent_count, 1)
        send_mail_mock.assert_called_once()
        confirm_mock.assert_not_called()  # no duplicate staff copy
        email_log = EmailLog.objects.get(idempotency_key=key)
        self.assertEqual(email_log.delivery_status, EmailLog.DELIVERY_STATUS_SENT)
        self.assertEqual(email_log.error_message, "")

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

    @patch(
        "clients.services.email_campaigns.send_mail",
        side_effect=RuntimeError("smtp failure for email-user@example.com"),
    )
    def test_process_email_campaign_redacts_failed_recipient_details(self, _send_mail_mock):
        campaign = EmailCampaign.objects.create(
            subject="News",
            message="Body",
            total_recipients=1,
            recipient_emails=["email-user@example.com"],
            created_by=self.staff,
        )

        call_command("process_email_campaigns", campaign_id=campaign.pk)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, EmailCampaign.STATUS_FAILED)
        self.assertEqual(campaign.failed_count, 1)
        self.assertIn("recipient #1: RuntimeError", campaign.error_details)
        self.assertNotIn("email-user@example.com", campaign.error_details)
        self.assertNotIn("smtp failure", campaign.error_details)


    @override_settings(EMAIL_CAMPAIGN_STALE_AFTER_MINUTES=30)
    @patch("clients.services.email_campaigns._send_confirmation_email")
    @patch("clients.services.email_campaigns.send_mail", return_value=1)
    def test_stale_running_campaign_can_be_reclaimed(self, send_mail_mock, _confirm_mock):
        campaign = EmailCampaign.objects.create(
            subject="Stale",
            message="Body",
            total_recipients=1,
            recipient_emails=["email-user@example.com"],
            created_by=self.staff,
            status=EmailCampaign.STATUS_RUNNING,
            started_at=timezone.now() - timedelta(minutes=45),
        )

        from clients.services.email_campaigns import process_campaign

        result = process_campaign(campaign.pk)

        self.assertIsNotNone(result)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, EmailCampaign.STATUS_COMPLETED)
        self.assertEqual(campaign.sent_count, 1)
        send_mail_mock.assert_called_once()

    @override_settings(EMAIL_CAMPAIGN_STALE_AFTER_MINUTES=30)
    @patch("clients.services.email_campaigns.send_mail", return_value=1)
    def test_fresh_running_campaign_is_not_claimed(self, send_mail_mock):
        campaign = EmailCampaign.objects.create(
            subject="Fresh",
            message="Body",
            total_recipients=1,
            recipient_emails=["email-user@example.com"],
            created_by=self.staff,
            status=EmailCampaign.STATUS_RUNNING,
            started_at=timezone.now(),
        )

        from clients.services.email_campaigns import process_campaign

        result = process_campaign(campaign.pk)

        self.assertIsNone(result)
        send_mail_mock.assert_not_called()

    @override_settings(EMAIL_CAMPAIGN_STALE_AFTER_MINUTES=30)
    @patch("clients.services.email_campaigns._send_confirmation_email")
    @patch("clients.services.email_campaigns.send_mail", return_value=1)
    def test_stale_reclaim_does_not_duplicate_already_sent_recipient(self, send_mail_mock, _confirm_mock):
        recipients = ["sent@example.com", "pending@example.com"]
        campaign = EmailCampaign.objects.create(
            subject="Resume",
            message="Body",
            total_recipients=2,
            recipient_emails=recipients,
            created_by=self.staff,
            status=EmailCampaign.STATUS_RUNNING,
            started_at=timezone.now() - timedelta(minutes=45),
        )
        EmailLog.objects.create(
            subject="Resume",
            body="Body",
            recipients="sent@example.com",
            template_type="mass_email",
            delivery_status=EmailLog.DELIVERY_STATUS_SENT,
            idempotency_key=build_email_idempotency_key("mass_email", campaign.pk, "sent@example.com"),
        )

        from clients.services.email_campaigns import process_campaign

        result = process_campaign(campaign.pk)

        self.assertIsNotNone(result)
        self.assertEqual(send_mail_mock.call_count, 1)
        self.assertEqual(send_mail_mock.call_args.args[3], ["pending@example.com"])
        campaign.refresh_from_db()
        self.assertEqual(campaign.sent_count, 2)

    @override_settings(EMAIL_CAMPAIGN_STALE_AFTER_MINUTES=30)
    @patch("clients.services.email_campaigns._send_confirmation_email")
    @patch("clients.services.email_campaigns.send_mail", return_value=1)
    def test_failed_recipient_is_retried_on_stale_reclaim(self, send_mail_mock, _confirm_mock):
        campaign = EmailCampaign.objects.create(
            subject="Retry",
            message="Body",
            total_recipients=1,
            recipient_emails=["retry@example.com"],
            created_by=self.staff,
            status=EmailCampaign.STATUS_RUNNING,
            started_at=timezone.now() - timedelta(minutes=45),
        )
        EmailLog.objects.create(
            subject="Retry",
            body="Body",
            recipients="retry@example.com",
            template_type="mass_email",
            delivery_status=EmailLog.DELIVERY_STATUS_FAILED,
            idempotency_key=build_email_idempotency_key("mass_email", campaign.pk, "retry@example.com"),
        )

        from clients.services.email_campaigns import process_campaign

        result = process_campaign(campaign.pk)

        self.assertIsNotNone(result)
        send_mail_mock.assert_called_once()
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, EmailCampaign.STATUS_COMPLETED)
        self.assertEqual(campaign.sent_count, 1)

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
