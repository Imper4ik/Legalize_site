from __future__ import annotations

import os
from unittest.mock import patch

from django.test import Client as DjangoClient
from django.test import TestCase
from django.urls import reverse

from clients.models import EmailCampaign
from legalize_site.backups import BackupResult


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

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    def test_db_backup_cron_is_csrf_exempt_but_still_requires_token(self):
        csrf_client = DjangoClient(enforce_csrf_checks=True)

        response = csrf_client.post(reverse("db_backup"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "forbidden"})

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("legalize_site.cron_views.create_db_backup")
    def test_db_backup_cron_accepts_header_token_with_csrf_checks(self, create_backup_mock):
        create_backup_mock.return_value = BackupResult(
            backup_id="backup-20260428-020000",
            path="/tmp/backup.sql.enc",
            size_bytes=123,
            plaintext_sha256="abc123",
            stored_file_sha256="abc123",
            encrypted=True,
            stored_remotely=True,
        )
        csrf_client = DjangoClient(enforce_csrf_checks=True)

        response = csrf_client.post(
            reverse("db_backup"),
            HTTP_X_CRON_TOKEN="secret",
            REMOTE_ADDR="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "backup created")
        create_backup_mock.assert_called_once()

    @patch.dict(os.environ, {"BACKUP_TRIGGER_SECRET": "legacy-secret"}, clear=True)
    @patch("legalize_site.cron_views.create_db_backup")
    def test_db_backup_cron_accepts_legacy_backup_trigger_secret(self, create_backup_mock):
        create_backup_mock.return_value = BackupResult(
            backup_id="backup-20260428-020000",
            path="/tmp/backup.sql.enc",
            size_bytes=123,
            plaintext_sha256="abc123",
            stored_file_sha256="abc123",
            encrypted=True,
            stored_remotely=True,
        )
        csrf_client = DjangoClient(enforce_csrf_checks=True)

        response = csrf_client.post(
            reverse("db_backup"),
            HTTP_AUTHORIZATION="Bearer legacy-secret",
            REMOTE_ADDR="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "backup created")
        create_backup_mock.assert_called_once()

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    def test_process_document_jobs_cron_requires_token(self):
        response = self.client.post(reverse("process_document_jobs_cron"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "forbidden"})

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("django.core.management.call_command")
    def test_process_document_jobs_cron_calls_command(self, call_command_mock):
        response = self.client.post(
            reverse("process_document_jobs_cron"),
            data={"limit": "5"},
            HTTP_X_CRON_TOKEN="secret",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "processed")
        call_command_mock.assert_called_once_with("process_document_jobs", "--limit", "5")

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("django.core.management.call_command")
    def test_process_document_jobs_cron_invalid_limit(self, call_command_mock):
        response = self.client.post(
            reverse("process_document_jobs_cron"),
            data={"limit": "invalid"},
            HTTP_X_CRON_TOKEN="secret",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid limit")
        call_command_mock.assert_not_called()

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("django.core.management.call_command")
    def test_process_document_jobs_cron_negative_limit(self, call_command_mock):
        response = self.client.post(
            reverse("process_document_jobs_cron"),
            data={"limit": "-5"},
            HTTP_X_CRON_TOKEN="secret",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "limit must be positive")
        call_command_mock.assert_not_called()

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("django.core.management.call_command")
    def test_process_document_jobs_cron_large_limit(self, call_command_mock):
        response = self.client.post(
            reverse("process_document_jobs_cron"),
            data={"limit": "150"},
            HTTP_X_CRON_TOKEN="secret",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "processed")
        call_command_mock.assert_called_once_with("process_document_jobs", "--limit", "100")

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("django.core.management.call_command")
    def test_process_document_jobs_cron_bearer_token(self, call_command_mock):
        response = self.client.post(
            reverse("process_document_jobs_cron"),
            HTTP_AUTHORIZATION="Bearer secret",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(response.status_code, 200)
        call_command_mock.assert_called_once_with("process_document_jobs")

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    def test_update_reminders_cron_requires_token(self):
        response = self.client.post(reverse("update_reminders_cron"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "forbidden"})

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("django.core.management.call_command")
    def test_update_reminders_cron_calls_command(self, call_command_mock):
        response = self.client.post(
            reverse("update_reminders_cron"),
            data={"only": ["documents", "payments"]},
            HTTP_X_CRON_TOKEN="secret",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "processed")
        call_command_mock.assert_called_once_with("update_reminders", "--only", "documents", "--only", "payments")

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("django.core.management.call_command")
    def test_update_reminders_cron_bearer_token(self, call_command_mock):
        response = self.client.post(
            reverse("update_reminders_cron"),
            HTTP_AUTHORIZATION="Bearer secret",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(response.status_code, 200)
        call_command_mock.assert_called_once_with("update_reminders")
