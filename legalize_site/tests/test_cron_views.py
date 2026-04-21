from __future__ import annotations

import os
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from clients.models import EmailCampaign


class CronViewsTests(TestCase):
    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    def test_process_email_campaigns_cron_requires_token(self):
        response = self.client.post(reverse("process_email_campaigns_cron"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "forbidden"})

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("clients.services.email_campaigns._log_email")
    @patch("clients.services.email_campaigns._send_confirmation_email")
    @patch("clients.services.email_campaigns.send_mail", return_value=1)
    def test_process_email_campaigns_cron_processes_pending_campaigns(
        self,
        send_mail_mock,
        confirm_mock,
        log_mock,
    ):
        campaign = EmailCampaign.objects.create(
            subject="Queued",
            message="Body",
            total_recipients=1,
            recipient_emails=["queued@example.com"],
        )

        response = self.client.post(
            reverse("process_email_campaigns_cron"),
            data={"limit": "1"},
            HTTP_X_CRON_TOKEN="secret",
            REMOTE_ADDR="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "processed")
        self.assertEqual(payload["processed_count"], 1)
        self.assertEqual(payload["campaigns"][0]["campaign_id"], campaign.pk)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, EmailCampaign.STATUS_COMPLETED)
        self.assertEqual(campaign.sent_count, 1)
        send_mail_mock.assert_called_once()
        confirm_mock.assert_called_once()
        log_mock.assert_called_once()
