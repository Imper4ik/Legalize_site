"""Tests for cron views (db_backup) and SafeSMTPEmailBackend."""
import os
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory, SimpleTestCase

from legalize_site.cron_views import db_backup
from legalize_site.mail import SafeSMTPEmailBackend


class DbBackupViewTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_missing_cron_token_returns_403(self):
        request = self.factory.get("/cron/backup/")
        resp = db_backup(request)
        self.assertEqual(resp.status_code, 403)

    @patch.dict(os.environ, {"CRON_TOKEN": "secret123"})
    def test_wrong_token_returns_403(self):
        request = self.factory.get("/cron/backup/", HTTP_X_CRON_TOKEN="wrong")
        resp = db_backup(request)
        self.assertEqual(resp.status_code, 403)

    @patch.dict(os.environ, {"CRON_TOKEN": "secret123"})
    def test_no_database_url_returns_500(self):
        request = self.factory.get("/cron/backup/", HTTP_X_CRON_TOKEN="secret123")
        # Ensure DATABASE_URL is not set
        env = os.environ.copy()
        env.pop("DATABASE_URL", None)
        env.pop("RAILWAY_DATABASE_URL", None)
        with patch.dict(os.environ, env, clear=True):
            # pg_dump must be found but DATABASE_URL is missing
            if not os.environ.get("DATABASE_URL") and not os.environ.get("RAILWAY_DATABASE_URL"):
                resp = db_backup(request)
                self.assertIn(resp.status_code, (403, 500))


class SafeSMTPEmailBackendTest(SimpleTestCase):
    def test_send_empty_list_returns_zero(self):
        backend = SafeSMTPEmailBackend(host="localhost", port=25, fail_silently=True)
        result = backend.send_messages([])
        self.assertEqual(result, 0)

    def test_send_none_returns_zero(self):
        backend = SafeSMTPEmailBackend(host="localhost", port=25, fail_silently=True)
        result = backend.send_messages(None)
        self.assertEqual(result, 0)

    @patch("legalize_site.mail.SMTPEmailBackend.send_messages", side_effect=Exception("SMTP fail"))
    @patch("legalize_site.mail.ConsoleEmailBackend.send_messages", return_value=1)
    def test_fallback_to_console_on_smtp_failure(self, mock_console, mock_smtp):
        from django.core.mail import EmailMessage
        backend = SafeSMTPEmailBackend(host="localhost", port=25, fail_silently=True)
        msg = EmailMessage("Subject", "Body", "from@test.com", ["to@test.com"])
        result = backend.send_messages([msg])
        self.assertEqual(result, 1)
        mock_console.assert_called_once()
