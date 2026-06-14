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

    def test_onboarding_travel_validates_legal_stay_until(self):
        import uuid

        from clients.models import ClientOnboardingSession
        from clients.services.onboarding_tokens import hash_onboarding_token

        client = Client.objects.create(first_name="Test", last_name="User", email="test-travel@example.com")
        User = get_user_model()
        user = User.objects.create_user(email=client.email, password="password123")
        client.user = user
        client.save()
        self.client.force_login(user)

        token = uuid.uuid4().hex
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hash_onboarding_token(token),
            expires_at=timezone.now() + timedelta(days=1),
        )

        mos_data = client.mos_application_data
        mos_data.status = "client_filling"
        mos_data.save()

        # Test valid date format
        url = reverse("clients:onboarding_travel", kwargs={"token": token})
        response = self.client.post(
            url,
            {
                "legal_stay_until": "2026-12-31",
                "is_in_poland": "yes",
                "last_entry_date": "2026-01-01",
                "stay_basis": "visa",
                "was_in_poland_before": "no",
                "has_insurance": "yes",
                "has_stable_income": "yes",
            }
        )
        self.assertEqual(response.status_code, 302)
        mos_data.refresh_from_db()
        self.assertEqual(mos_data.legal_stay_until.strftime("%Y-%m-%d"), "2026-12-31")

        # Test invalid date format
        response = self.client.post(
            url,
            {
                "legal_stay_until": "not-a-date",
                "is_in_poland": "yes",
                "last_entry_date": "2026-01-01",
                "stay_basis": "visa",
                "was_in_poland_before": "no",
                "has_insurance": "yes",
                "has_stable_income": "yes",
            }
        )
        self.assertEqual(response.status_code, 400)

        # Test empty legal_stay_until (should clear/set to None)
        response = self.client.post(
            url,
            {
                "legal_stay_until": "",
                "is_in_poland": "yes",
                "last_entry_date": "2026-01-01",
                "stay_basis": "visa",
                "was_in_poland_before": "no",
                "has_insurance": "yes",
                "has_stable_income": "yes",
            }
        )
        self.assertEqual(response.status_code, 302)
        mos_data.refresh_from_db()
        self.assertIsNone(mos_data.legal_stay_until)

    def test_onboarding_document_delete_requires_post(self):
        import uuid

        from clients.models import ClientOnboardingSession
        from clients.services.onboarding_tokens import hash_onboarding_token

        client = Client.objects.create(first_name="Test", last_name="User", email="test-doc-del@example.com")
        User = get_user_model()
        user = User.objects.create_user(email=client.email, password="password123")
        client.user = user
        client.save()
        self.client.force_login(user)

        token = uuid.uuid4().hex
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hash_onboarding_token(token),
            expires_at=timezone.now() + timedelta(days=1),
        )
        doc = Document.objects.create(
            client=client,
            document_type=DocumentType.PASSPORT.value,
        )

        # Test GET method is rejected
        url = reverse("clients:onboarding_document_delete", kwargs={"token": token, "doc_id": doc.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405) # Method Not Allowed

        # Test POST method is accepted
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Document.objects.filter(pk=doc.pk).exists())

    def test_document_pii_scrubbing_masks_nip_and_clears_detected_names(self):
        client = Client.objects.create(first_name="Test", last_name="User", email="test@example.com")
        doc = Document.objects.create(
            client=client,
            document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            parsed_data={
                "employer_nip": "1234567890",
                "detected_names": ["Test User", "Employer Name"],
                "full_name": "Test User",
                "text": "Raw OCR text of ZUS document",
            }
        )

        # Trigger scrub_parsed_pii
        doc.scrub_parsed_pii()

        # Check that PII keys are removed/scrubbed
        self.assertNotIn("full_name", doc.parsed_data)
        self.assertNotIn("text", doc.parsed_data)

        # Check that NIP is masked keeping first 2 and last 2 characters
        self.assertEqual(doc.parsed_data["employer_nip"], "12******90")

        # Check that detected_names is cleared (empty list)
        self.assertEqual(doc.parsed_data["detected_names"], [])
        self.assertTrue(doc.parsed_data.get("pii_scrubbed"))
