from __future__ import annotations

from datetime import timedelta

from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from clients.models import EmailCampaign, EmailLog
from clients.services.email_campaigns import process_campaign, queue_mass_email_campaign


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

    def test_email_campaign_recipients_not_plaintext_and_readable(self):
        campaign = queue_mass_email_campaign(
            subject="Subj",
            message="Body",
            recipient_emails=["client1@example.com", "client2@example.com"],
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT recipient_emails FROM clients_emailcampaign WHERE id = %s", [campaign.pk])
            (raw_recipients,) = cursor.fetchone()

        self.assertNotIn("client1@example.com", raw_recipients)
        campaign.refresh_from_db()
        self.assertEqual(campaign.recipient_emails_list, ["client1@example.com", "client2@example.com"])

    def test_campaign_processing_handles_empty_recipient_list(self):
        campaign = EmailCampaign.objects.create(subject="S", message="M", recipient_emails="[]")
        result = process_campaign(campaign.pk)
        self.assertIsNotNone(result)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, EmailCampaign.STATUS_FAILED)

    def test_campaign_recipient_legacy_invalid_value_does_not_crash(self):
        campaign = EmailCampaign.objects.create(subject="Legacy", message="Body", recipient_emails="not-json")
        self.assertEqual(campaign.recipient_emails_list, ["not-json"])

    def test_reencrypt_command_reencrypts_raw_plaintext_records(self):
        log = EmailLog.objects.create(subject="Re", body="Sensitive", recipients="one@example.com")
        campaign = EmailCampaign.objects.create(subject="Camp", message="Message", recipient_emails='["a@example.com"]')

        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE clients_emaillog SET body=%s, recipients=%s, error_message=%s WHERE id=%s",
                ["plain-body", "plain@example.com", "plain-error", log.pk],
            )
            cursor.execute(
                "UPDATE clients_emailcampaign SET message=%s, error_details=%s, recipient_emails=%s WHERE id=%s",
                ["plain-message", "plain-details", '["plain@example.com"]', campaign.pk],
            )

        call_command("reencrypt_email_sensitive_data")

        with connection.cursor() as cursor:
            cursor.execute("SELECT body, recipients FROM clients_emaillog WHERE id = %s", [log.pk])
            raw_body, raw_recipients = cursor.fetchone()
            self.assertNotEqual(raw_body, "plain-body")
            self.assertNotEqual(raw_recipients, "plain@example.com")

            cursor.execute("SELECT message, recipient_emails FROM clients_emailcampaign WHERE id = %s", [campaign.pk])
            raw_message, raw_campaign_recipients = cursor.fetchone()
            self.assertNotEqual(raw_message, "plain-message")
            self.assertNotIn("plain@example.com", raw_campaign_recipients)

        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(log.body, "plain-body")
        self.assertEqual(log.recipients, "plain@example.com")
        self.assertEqual(campaign.message, "plain-message")
        self.assertEqual(campaign.recipient_emails_list, ["plain@example.com"])
