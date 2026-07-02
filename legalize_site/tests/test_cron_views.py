from __future__ import annotations

import os
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import Client as DjangoClient
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from clients.models import Client, EmailCampaign, EmailLog
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
    """/cron/run-maintenance/ — GDPR retention wiring (cleanup + anonymization)."""

    @staticmethod
    def _make_old_client(email: str, years: int = 6) -> Client:
        client = Client.objects.create(
            first_name="Old",
            last_name="Client",
            citizenship="UA",
            phone="+48111111111",
            email=email,
        )
        Client.all_objects.filter(pk=client.pk).update(
            created_at=timezone.now() - timedelta(days=years * 365 + 30)
        )
        client.refresh_from_db()
        return client

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
    def test_default_run_cleans_email_logs_but_only_dry_runs_anonymization(self):
        old_client = self._make_old_client("old-dryrun@example.com")
        log = EmailLog.objects.create(
            client=old_client,
            subject="Old email",
            body="sensitive body",
            recipients="old-dryrun@example.com",
        )
        EmailLog.objects.filter(pk=log.pk).update(sent_at=timezone.now() - timedelta(days=400))

        response = self._post()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "run_maintenance")
        self.assertFalse(payload["anonymize_enabled"])
        self.assertEqual(payload["anonymize_years"], 5)

        log.refresh_from_db()
        self.assertEqual(log.body, "")
        self.assertEqual(log.recipients, "")

        old_client.refresh_from_db()
        self.assertEqual(old_client.first_name, "Old")
        self.assertEqual(old_client.email, "old-dryrun@example.com")

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @override_settings(AUTO_ANONYMIZE_OLD_CLIENTS=True, ANONYMIZE_CLIENTS_AFTER_YEARS=5)
    def test_opt_in_flag_anonymizes_old_clients_and_keeps_recent_ones(self):
        old_client = self._make_old_client("old-live@example.com")
        recent_client = Client.objects.create(
            first_name="Recent",
            last_name="Client",
            citizenship="UA",
            phone="+48222222222",
            email="recent-live@example.com",
        )

        response = self._post()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["anonymize_enabled"])

        old_client.refresh_from_db()
        self.assertEqual(old_client.first_name, f"Anonymized_{old_client.pk}")
        self.assertEqual(old_client.email, f"deleted_{old_client.pk}@example.com")

        recent_client.refresh_from_db()
        self.assertEqual(recent_client.first_name, "Recent")
        self.assertEqual(recent_client.email, "recent-live@example.com")

    @patch.dict(os.environ, {"CRON_TOKEN": "secret"}, clear=False)
    @patch("legalize_site.cron_views._alert_cron_failure")
    @patch("django.core.management.call_command", side_effect=RuntimeError("db unavailable"))
    def test_run_maintenance_cron_exception_is_generic_and_alerts(self, _call_mock, alert_mock):
        response = self._post()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": "retention maintenance failed"})
        alert_mock.assert_called_once()
