from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.template import Context, Template
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from clients.constants import DocumentType
from clients.forms import StaffUserCreateForm
from clients.management.commands.update_reminders import Command
from clients.models import Client, Document, EmailLog, Reminder
from clients.security.sanitizer import sanitize_user_html
from clients.services.notifications import _send_email
from clients.services.roles import ensure_predefined_roles
from clients.services.zus import missing_zus_months


class RemainingAuditHardeningTests(TestCase):
    def setUp(self):
        ensure_predefined_roles()
        User = get_user_model()
        self.staff = User.objects.create_user(email="staff-audit@example.com", password="securepassword", is_staff=True)
        self.staff.groups.add(Group.objects.get(name="Staff"))
        self.admin = User.objects.create_user(email="admin-audit@example.com", password="securepassword", is_staff=True)
        self.admin.groups.add(Group.objects.get(name="Admin"))


    def test_background_automation_loop_defaults_to_disabled(self):
        self.assertIn('ENABLE_BACKGROUND_AUTOMATION_LOOP:=false', Path("start.sh").read_text())

    def test_querystring_replace_preserves_and_encodes_filters(self):
        request = RequestFactory().get("/staff/?q=A%26B&company=7&document=ocr_review&page=2")
        rendered = Template(
            "{% load querystring_tags %}{% querystring_replace page=3 %}"
        ).render(Context({"request": request}))

        self.assertIn("q=A%26B", rendered)
        self.assertIn("company=7", rendered)
        self.assertIn("document=ocr_review", rendered)
        self.assertIn("page=3", rendered)

    def test_email_log_date_filter_uses_full_day_range(self):
        client = Client.objects.create(first_name="Log", last_name="Client")
        included = EmailLog.objects.create(client=client, subject="Included", body="Body", recipients="a@example.com")
        excluded = EmailLog.objects.create(client=client, subject="Excluded", body="Body", recipients="b@example.com")
        EmailLog.objects.filter(pk=included.pk).update(sent_at=timezone.make_aware(datetime(2026, 5, 31, 23, 59)))
        EmailLog.objects.filter(pk=excluded.pk).update(sent_at=timezone.make_aware(datetime(2026, 6, 1, 0, 0)))

        self.client.login(email="admin-audit@example.com", password="securepassword")
        response = self.client.get(reverse("clients:email_logs"), {"date_start": "2026-05-31", "date_end": "2026-05-31"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Included")
        self.assertNotContains(response, "Excluded")

    def test_staff_calculator_requires_login(self):
        response = self.client.get(reverse("clients:calculator"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    @patch("clients.services.calculator.get_eur_to_pln_rate", return_value=4.2)
    def test_staff_calculator_allows_staff_user(self, _rate_mock):
        self.client.login(email="staff-audit@example.com", password="securepassword")
        response = self.client.get(reverse("clients:calculator"))
        self.assertEqual(response.status_code, 200)

    @override_settings(
        AUTH_PASSWORD_VALIDATORS=[
            {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
        ]
    )
    def test_staff_user_create_form_runs_password_validators(self):
        form = StaffUserCreateForm(
            data={
                "email": "weak@example.com",
                "first_name": "Weak",
                "last_name": "User",
                "is_staff": "on",
                "is_active": "on",
                "password1": "short",
                "password2": "short",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("12", str(form.errors))

    def test_sponsor_self_and_cycles_are_rejected_by_model_validation(self):
        sponsor = Client.objects.create(first_name="Sponsor", last_name="One")
        member = Client.objects.create(first_name="Member", last_name="Two", sponsor_client=sponsor)

        sponsor.sponsor_client = sponsor
        with self.assertRaises(ValidationError):
            sponsor.full_clean()

        sponsor.sponsor_client = member
        with self.assertRaises(ValidationError):
            sponsor.full_clean()

    def test_unverified_health_insurance_does_not_cover_zus_month(self):
        client = Client.objects.create(
            first_name="Zus",
            last_name="Client",
            workflow_stage="waiting_decision",
            fingerprints_date=date(2026, 2, 10),
        )
        Document.objects.create(
            client=client,
            document_type=DocumentType.HEALTH_INSURANCE.value,
            expiry_date=date(2026, 5, 31),
            verified=False,
        )

        self.assertEqual(
            missing_zus_months(client, today=date(2026, 5, 15)),
            [date(2026, 3, 1), date(2026, 4, 1)],
        )

        client.documents.update(verified=True)
        self.assertEqual(missing_zus_months(client, today=date(2026, 5, 15)), [])

    def test_legal_stay_reminder_updates_existing_active_reminder(self):
        client = Client.objects.create(first_name="Legal", last_name="Stay", workflow_stage="document_collection")
        mos_data = client.mos_application_data
        mos_data.legal_stay_until = timezone.localdate() + timedelta(days=20)
        mos_data.save(update_fields=["legal_stay_until"])
        command = Command()

        command.create_legal_stay_reminders()
        reminder = Reminder.objects.get(client=client, reminder_type="legal_stay", is_active=True)
        first_due_date = reminder.due_date

        mos_data.legal_stay_until = timezone.localdate() + timedelta(days=30)
        mos_data.save(update_fields=["legal_stay_until"])
        command.create_legal_stay_reminders()

        self.assertEqual(Reminder.objects.filter(client=client, reminder_type="legal_stay", is_active=True).count(), 1)
        reminder.refresh_from_db()
        self.assertNotEqual(reminder.due_date, first_due_date)

    @override_settings(EMAIL_SEND_RETRY_ATTEMPTS=2, EMAIL_SEND_RETRY_BACKOFF_SECONDS=0)
    @patch("clients.services.notifications._send_confirmation_email")
    @patch("clients.services.notifications.send_mail")
    def test_notification_email_retries_transient_smtp_failure(self, send_mail_mock, _confirm_mock):
        send_mail_mock.side_effect = [RuntimeError("temporary"), 1]
        client = Client.objects.create(first_name="Email", last_name="Retry", email="retry@example.com")

        sent = _send_email("Subject", "Body", ["retry@example.com"], client=client, idempotency_key="retry-key")

        self.assertEqual(sent, 1)
        self.assertEqual(send_mail_mock.call_count, 2)

    def test_sanitize_user_html_strips_scripts_and_dangerous_attributes(self):
        cleaned = sanitize_user_html('<p onclick="evil()">ok</p><script>alert(1)</script><strong>yes</strong>')
        self.assertIn("<p>ok</p>", cleaned)
        self.assertIn("<strong>yes</strong>", cleaned)
        self.assertNotIn("onclick", cleaned)
        self.assertNotIn("<script", cleaned)
