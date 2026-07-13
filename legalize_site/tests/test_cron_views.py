from __future__ import annotations

import os
from types import SimpleNamespace
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
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "process_email_campaigns")
        self.assertIn("duration_ms", payload)
        self.assertEqual(payload["processed_count"], 1)
        self.assertEqual(payload["campaigns"][0]["campaign_id"], campaign.pk)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, EmailCampaign.STATUS_COMPLETED)
        self.assertEqual(campaign.sent_count, 1)
        send_mail_mock.assert_called_once()
        confirm_mock.assert_called_once()
        log_mock.assert_called_once()

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("legalize_site.cron_views.process_pending_email_campaigns")
    def test_process_email_campaigns_cron_rejects_non_positive_limit(self, process_mock):
        response = self.client.post(
            reverse("process_email_campaigns_cron"),
            data={"limit": "0"},
            HTTP_X_CRON_TOKEN="secret",
            REMOTE_ADDR="127.0.0.1",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "limit must be positive")
        process_mock.assert_not_called()

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("legalize_site.cron_views.process_pending_email_campaigns", return_value=[])
    def test_process_email_campaigns_cron_clamps_large_limit(self, process_mock):
        response = self.client.post(
            reverse("process_email_campaigns_cron"),
            data={"limit": "150"},
            HTTP_X_CRON_TOKEN="secret",
            REMOTE_ADDR="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["processed_count"], 0)
        process_mock.assert_called_once_with(limit=100)

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("legalize_site.cron_views._alert_cron_failure")
    @patch("legalize_site.cron_views.process_pending_email_campaigns")
    def test_process_email_campaigns_cron_alerts_on_failed_campaign(self, process_mock, alert_mock):
        process_mock.return_value = [
            SimpleNamespace(
                campaign_id=42,
                status=EmailCampaign.STATUS_FAILED,
                sent_count=0,
                failed_count=1,
            )
        ]

        response = self.client.post(
            reverse("process_email_campaigns_cron"),
            HTTP_X_CRON_TOKEN="secret",
            REMOTE_ADDR="127.0.0.1",
        )

        payload = response.json()
        self.assertEqual(response.status_code, 500)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["processed_count"], 1)
        self.assertEqual(payload["errors"], ["campaign_id=42 status=failed failed_count=1"])
        alert_mock.assert_called_once()

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
        self.assertIs(response.json()["stored_remotely"], True)
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

    @patch.dict(
        os.environ,
        {"CRON_TOKEN": "cron-secret", "BACKUP_TRIGGER_SECRET": "legacy-secret"},
        clear=True,
    )
    @patch("legalize_site.cron_views.process_pending_document_jobs")
    def test_backup_trigger_secret_cannot_authorize_non_backup_cron(self, process_mock):
        response = self.client.post(
            reverse("process_document_jobs_cron"),
            HTTP_X_CRON_TOKEN="legacy-secret",
            REMOTE_ADDR="127.0.0.1",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "forbidden"})
        process_mock.assert_not_called()

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    def test_process_document_jobs_cron_requires_token(self):
        response = self.client.post(reverse("process_document_jobs_cron"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "forbidden"})

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("legalize_site.cron_views.reclaim_stale_document_jobs", return_value=0)
    @patch("legalize_site.cron_views.process_pending_document_jobs", return_value=[])
    def test_process_document_jobs_cron_processes_jobs(self, process_mock, reclaim_mock):
        response = self.client.post(
            reverse("process_document_jobs_cron"),
            data={"limit": "5"},
            HTTP_X_CRON_TOKEN="secret",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "processed")
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["command"], "process_document_jobs")
        self.assertEqual(response.json()["processed_count"], 0)
        self.assertEqual(response.json()["reclaimed_count"], 0)
        reclaim_mock.assert_called_once()
        self.assertEqual(process_mock.call_args.kwargs["limit"], 5)

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("legalize_site.cron_views.process_pending_document_jobs")
    def test_process_document_jobs_cron_invalid_limit(self, process_mock):
        response = self.client.post(
            reverse("process_document_jobs_cron"),
            data={"limit": "invalid"},
            HTTP_X_CRON_TOKEN="secret",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid limit")
        process_mock.assert_not_called()

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("legalize_site.cron_views.process_pending_document_jobs")
    def test_process_document_jobs_cron_negative_limit(self, process_mock):
        response = self.client.post(
            reverse("process_document_jobs_cron"),
            data={"limit": "-5"},
            HTTP_X_CRON_TOKEN="secret",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "limit must be positive")
        process_mock.assert_not_called()

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("legalize_site.cron_views.reclaim_stale_document_jobs", return_value=0)
    @patch("legalize_site.cron_views.process_pending_document_jobs", return_value=[])
    def test_process_document_jobs_cron_large_limit(self, process_mock, _reclaim_mock):
        response = self.client.post(
            reverse("process_document_jobs_cron"),
            data={"limit": "150"},
            HTTP_X_CRON_TOKEN="secret",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "processed")
        self.assertEqual(response.json()["processed_count"], 0)
        self.assertEqual(process_mock.call_args.kwargs["limit"], 100)

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("legalize_site.cron_views.reclaim_stale_document_jobs", return_value=0)
    @patch("legalize_site.cron_views.process_pending_document_jobs", return_value=[])
    def test_process_document_jobs_cron_bearer_token(self, process_mock, _reclaim_mock):
        response = self.client.post(
            reverse("process_document_jobs_cron"),
            HTTP_AUTHORIZATION="Bearer secret",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["command"], "process_document_jobs")
        self.assertIsNone(process_mock.call_args.kwargs["limit"])

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("legalize_site.cron_views._alert_cron_failure")
    @patch("legalize_site.cron_views.reclaim_stale_document_jobs", return_value=2)
    @patch("legalize_site.cron_views.process_pending_document_jobs")
    def test_process_document_jobs_cron_alerts_on_failed_job(self, process_mock, reclaim_mock, alert_mock):
        process_mock.return_value = [SimpleNamespace(job=SimpleNamespace(id=9), status="failed")]

        response = self.client.post(
            reverse("process_document_jobs_cron"),
            HTTP_X_CRON_TOKEN="secret",
            REMOTE_ADDR="127.0.0.1",
        )

        payload = response.json()
        self.assertEqual(response.status_code, 500)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["reclaimed_count"], 2)
        self.assertEqual(payload["errors"], ["job_id=9 status=failed"])
        reclaim_mock.assert_called_once()
        alert_mock.assert_called_once()

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("legalize_site.cron_views._alert_cron_failure")
    @patch("legalize_site.cron_views.reclaim_stale_document_jobs", return_value=0)
    @patch("legalize_site.cron_views.process_pending_document_jobs", side_effect=RuntimeError("secret path"))
    def test_process_document_jobs_cron_exception_is_generic(self, _process_mock, _reclaim_mock, alert_mock):
        response = self.client.post(
            reverse("process_document_jobs_cron"),
            HTTP_X_CRON_TOKEN="secret",
            REMOTE_ADDR="127.0.0.1",
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": "document job processing failed"})
        alert_mock.assert_called_once()

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
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["command"], "update_reminders")
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

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    def test_retention_maintenance_cron_requires_token(self):
        response = self.client.post(reverse("retention_maintenance_cron"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "forbidden"})

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("django.core.management.call_command")
    def test_retention_maintenance_cron_calls_command(self, call_command_mock):
        response = self.client.post(
            reverse("retention_maintenance_cron"),
            HTTP_X_CRON_TOKEN="secret",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "processed")
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["command"], "run_retention_maintenance")
        call_command_mock.assert_called_once_with("run_retention_maintenance")

    @patch.dict(os.environ, {"CRON_TOKEN": "secret", "CRON_ALLOWED_IPS": "203.0.113.10"}, clear=False)
    @patch("legalize_site.cron_views.process_pending_email_campaigns")
    def test_cron_ip_allowlist_ignores_spoofed_x_forwarded_for(self, process_mock):
        response = self.client.post(
            reverse("process_email_campaigns_cron"),
            HTTP_X_CRON_TOKEN="secret",
            HTTP_X_FORWARDED_FOR="203.0.113.10",
            REMOTE_ADDR="198.51.100.44",
        )

        self.assertEqual(response.status_code, 403)
        process_mock.assert_not_called()

    @patch.dict(os.environ, {"CRON_TOKEN": "secret", "CRON_ALLOWED_IPS": "203.0.113.10"}, clear=False)
    @patch("legalize_site.cron_views.process_pending_email_campaigns", return_value=[])
    def test_cron_ip_allowlist_uses_remote_addr(self, process_mock):
        response = self.client.post(
            reverse("process_email_campaigns_cron"),
            HTTP_X_CRON_TOKEN="secret",
            HTTP_X_FORWARDED_FOR="198.51.100.44",
            REMOTE_ADDR="203.0.113.10",
        )

        self.assertEqual(response.status_code, 200)
        process_mock.assert_called_once()


class RunMaintenanceCronTests(TestCase):
    """The legacy URL remains a compatible alias for guarded retention."""

    def _post(self, **extra):
        return self.client.post(
            reverse("run_maintenance_cron"),
            HTTP_X_CRON_TOKEN="secret",
            REMOTE_ADDR="127.0.0.1",
            **extra,
        )

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    def test_run_maintenance_cron_requires_token(self):
        response = self.client.post(reverse("run_maintenance_cron"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "forbidden"})

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("django.core.management.call_command")
    def test_legacy_alias_calls_guarded_retention_command(self, call_command_mock):
        response = self._post()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "run_retention_maintenance")
        call_command_mock.assert_called_once_with("run_retention_maintenance")

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("legalize_site.cron_views._alert_cron_failure")
    @patch("django.core.management.call_command", side_effect=RuntimeError("db unavailable"))
    def test_run_maintenance_cron_exception_is_generic_and_alerts(self, _call_mock, alert_mock):
        response = self._post()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": "retention maintenance failed"})
        alert_mock.assert_called_once()
