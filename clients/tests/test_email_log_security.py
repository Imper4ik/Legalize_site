from __future__ import annotations

from datetime import timedelta

from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from clients.models import EmailLog


@override_settings(FERNET_KEYS=["MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="])
class EmailLogSecurityTests(TestCase):
    def test_body_and_recipients_not_stored_as_plaintext_and_readable_via_orm(self):
        log = EmailLog.objects.create(
            subject="Subject",
            body="Secret body",
            recipients="person@example.com",
            template_type="custom",
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT body, recipients FROM clients_emaillog WHERE id = %s", [log.pk])
            raw_body, raw_recipients = cursor.fetchone()

        self.assertNotEqual(raw_body, "Secret body")
        self.assertNotEqual(raw_recipients, "person@example.com")

        log.refresh_from_db()
        self.assertEqual(log.body, "Secret body")
        self.assertEqual(log.recipients, "person@example.com")

    @override_settings(EMAIL_LOG_BODY_RETENTION_DAYS=180)
    def test_retention_command_cleans_old_logs_and_new_logs_still_work(self):
        old_log = EmailLog.objects.create(subject="Old", body="Old body", recipients="old@example.com")
        EmailLog.objects.filter(pk=old_log.pk).update(sent_at=timezone.now() - timedelta(days=181))

        fresh_log = EmailLog.objects.create(subject="Fresh", body="Fresh body", recipients="fresh@example.com")

        call_command("cleanup_email_logs")

        old_log.refresh_from_db()
        fresh_log.refresh_from_db()

        self.assertEqual(old_log.body, "")
        self.assertEqual(old_log.recipients, "")
        self.assertEqual(fresh_log.body, "Fresh body")
        self.assertEqual(fresh_log.recipients, "fresh@example.com")
