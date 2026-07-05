from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clients.models import AppSettings, Client, ConsentRecord, MOSApplicationData
from clients.services.consent import record_onboarding_consent
from clients.services.onboarding_tokens import generate_onboarding_token


class ConsentRecordModelTests(TestCase):
    def setUp(self) -> None:
        self.client_record = Client.objects.create(
            first_name="Ola", last_name="Nowak", application_purpose="work"
        )

    def test_is_granted_reflects_latest_decision(self) -> None:
        purpose = ConsentRecord.Purpose.DATA_PROCESSING
        self.assertFalse(ConsentRecord.is_granted(self.client_record, purpose))

        ConsentRecord.record(client=self.client_record, purpose=purpose, granted=True)
        self.assertTrue(ConsentRecord.is_granted(self.client_record, purpose))

        # Withdrawal appends a new row and flips the current state.
        ConsentRecord.record(client=self.client_record, purpose=purpose, granted=False)
        self.assertFalse(ConsentRecord.is_granted(self.client_record, purpose))
        self.assertEqual(
            ConsentRecord.objects.filter(client=self.client_record, purpose=purpose).count(),
            2,
        )

    def test_current_status_returns_latest_per_purpose(self) -> None:
        ConsentRecord.record(
            client=self.client_record,
            purpose=ConsentRecord.Purpose.DATA_PROCESSING,
            granted=True,
        )
        ConsentRecord.record(
            client=self.client_record,
            purpose=ConsentRecord.Purpose.MARKETING,
            granted=True,
        )
        ConsentRecord.record(
            client=self.client_record,
            purpose=ConsentRecord.Purpose.MARKETING,
            granted=False,
        )
        status = ConsentRecord.current_status(self.client_record)
        self.assertTrue(status[ConsentRecord.Purpose.DATA_PROCESSING].granted)
        self.assertFalse(status[ConsentRecord.Purpose.MARKETING].granted)


class RecordOnboardingConsentServiceTests(TestCase):
    def setUp(self) -> None:
        self.client_record = Client.objects.create(
            first_name="Piotr", last_name="Zieba", application_purpose="work"
        )
        settings = AppSettings.get_solo()
        settings.privacy_policy_version = "2026-01"
        settings.save(update_fields=["privacy_policy_version"])

    def test_records_required_purposes_with_policy_version(self) -> None:
        created = record_onboarding_consent(client=self.client_record)
        self.assertEqual(len(created), 2)
        self.assertTrue(
            ConsentRecord.is_granted(self.client_record, ConsentRecord.Purpose.DATA_PROCESSING)
        )
        self.assertTrue(
            ConsentRecord.is_granted(self.client_record, ConsentRecord.Purpose.SERVICE_PROVISION)
        )
        self.assertEqual(created[0].policy_version, "2026-01")
        # Marketing is opt-in, never auto-granted at onboarding.
        self.assertFalse(
            ConsentRecord.is_granted(self.client_record, ConsentRecord.Purpose.MARKETING)
        )

    def test_is_idempotent_for_active_grants(self) -> None:
        record_onboarding_consent(client=self.client_record)
        again = record_onboarding_consent(client=self.client_record)
        self.assertEqual(again, [])
        self.assertEqual(ConsentRecord.objects.filter(client=self.client_record).count(), 2)


class AppSettingsControllerFieldsTests(TestCase):
    def test_new_data_controller_fields_persist(self) -> None:
        settings = AppSettings.get_solo()
        settings.legal_entity_name = "Kancelaria XYZ Sp. z o.o."
        settings.data_controller_nip = "1234567890"
        settings.representative_name = "Jan Kowalski, radca prawny"
        settings.dpo_contact = "iod@example.com"
        settings.privacy_policy_version = "2026-01"
        settings.save()

        reloaded = AppSettings.get_solo()
        self.assertEqual(reloaded.legal_entity_name, "Kancelaria XYZ Sp. z o.o.")
        self.assertEqual(reloaded.data_controller_nip, "1234567890")
        self.assertEqual(reloaded.representative_name, "Jan Kowalski, radca prawny")
        self.assertEqual(reloaded.dpo_contact, "iod@example.com")


class PortalConsentViewTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="subject@example.com", password="securepassword123"
        )
        self.client_record = Client.objects.create(
            first_name="Maria",
            last_name="Kowalska",
            email="subject@example.com",
            application_purpose="work",
            user=self.user,
        )
        raw, hashed = generate_onboarding_token()
        self.raw_token = raw
        from clients.models import ClientOnboardingSession

        ClientOnboardingSession.objects.create(
            client=self.client_record,
            token_hash=hashed,
            status="created",
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(self.user)
        self.url = reverse("clients:onboarding_consent", kwargs={"token": raw})

    def test_get_renders_consent_centre(self) -> None:
        ConsentRecord.record(
            client=self.client_record,
            purpose=ConsentRecord.Purpose.DATA_PROCESSING,
            granted=True,
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_post_withdraw_appends_row_and_flips_state(self) -> None:
        ConsentRecord.record(
            client=self.client_record,
            purpose=ConsentRecord.Purpose.DATA_PROCESSING,
            granted=True,
        )
        response = self.client.post(
            self.url,
            {"purpose": ConsentRecord.Purpose.DATA_PROCESSING, "action": "withdraw"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            ConsentRecord.is_granted(self.client_record, ConsentRecord.Purpose.DATA_PROCESSING)
        )
        latest = ConsentRecord.objects.filter(client=self.client_record).order_by("-created_at").first()
        self.assertEqual(latest.channel, ConsentRecord.Channel.PORTAL)

    def test_post_invalid_purpose_is_rejected(self) -> None:
        response = self.client.post(self.url, {"purpose": "bogus", "action": "grant"})
        self.assertEqual(response.status_code, 400)


class DeclarationsConsentGateTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="decl@example.com", password="securepassword123"
        )
        self.client_record = Client.objects.create(
            first_name="Igor",
            last_name="Petrov",
            email="decl@example.com",
            application_purpose="work",
            user=self.user,
        )
        self.case = self.client_record.cases.order_by("id").first()
        self.mos, _ = MOSApplicationData.objects.get_or_create(
            client=self.client_record, case=self.case
        )
        self.mos.status = "client_filling"
        self.mos.save(update_fields=["status"])
        raw, hashed = generate_onboarding_token()
        from clients.models import ClientOnboardingSession

        ClientOnboardingSession.objects.create(
            client=self.client_record,
            token_hash=hashed,
            status="created",
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(self.user)
        self.url = reverse("clients:onboarding_declarations", kwargs={"token": raw})

    def test_cannot_complete_without_consent(self) -> None:
        response = self.client.post(
            self.url, {"criminal_record": "no", "tax_arrears": "no"}
        )
        self.assertEqual(response.status_code, 200)
        self.mos.refresh_from_db()
        self.assertNotEqual(self.mos.status, "client_completed")
        self.assertFalse(
            ConsentRecord.is_granted(self.client_record, ConsentRecord.Purpose.DATA_PROCESSING)
        )

    def test_completing_with_consent_records_it(self) -> None:
        response = self.client.post(
            self.url,
            {"criminal_record": "no", "tax_arrears": "no", "rodo_consent": "on"},
        )
        self.assertEqual(response.status_code, 302)
        self.mos.refresh_from_db()
        self.assertEqual(self.mos.status, "client_completed")
        self.assertTrue(
            ConsentRecord.is_granted(self.client_record, ConsentRecord.Purpose.DATA_PROCESSING)
        )
