from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from clients.models import Client, Document, DocumentProcessingJob, EmailLog, Payment, Reminder


class SeedDemoDataCommandTests(TestCase):
    def test_requires_confirm_flag(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo_data", stdout=StringIO())

    @override_settings(
        IS_PRODUCTION=False,
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        },
    )
    def test_creates_safe_demo_records(self):
        out = StringIO()

        call_command("seed_demo_data", "--confirm", stdout=out)

        user = get_user_model().objects.get(email="demo-staff@example.test")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.groups.filter(name="Staff").exists())
        # email is encrypted (no SQL suffix match); the command seeds into an
        # otherwise empty test DB, so the total client count is the demo cohort.
        self.assertGreaterEqual(Client.objects.count(), 3)
        self.assertTrue(Document.objects.filter(awaiting_confirmation=True).exists())
        self.assertTrue(DocumentProcessingJob.objects.filter(requires_confirmation=True).exists())
        self.assertTrue(Payment.objects.exists())
        self.assertTrue(Reminder.objects.exists())
        self.assertTrue(EmailLog.objects.filter(idempotency_key="demo:missing-documents").exists())
        self.assertIn("Demo data created/updated.", out.getvalue())

    @override_settings(
        IS_PRODUCTION=False,
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        },
    )
    def test_rebinds_stale_idempotent_email_log_to_demo_case(self):
        call_command("seed_demo_data", "--confirm", stdout=StringIO())
        stale_owner = Client.objects.create(
            email="stale-demo-owner@example.test",
            first_name="Stale",
            last_name="Owner",
        )
        EmailLog.objects.filter(idempotency_key="demo:missing-documents").update(
            client=stale_owner,
            case=stale_owner.active_case,
        )

        call_command("seed_demo_data", "--confirm", stdout=StringIO())

        log = EmailLog.objects.get(idempotency_key="demo:missing-documents")
        self.assertEqual(log.client.email, "demo.waiting@example.test")
        self.assertEqual(log.case.client_id, log.client_id)

    @override_settings(IS_PRODUCTION=True)
    def test_blocks_production_without_explicit_override(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo_data", "--confirm", stdout=StringIO())
