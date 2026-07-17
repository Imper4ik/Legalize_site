from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import include, path, reverse
from django.utils import timezone

from clients.constants import DocumentType
from clients.models import (
    Client,
    ClientDigitalAccess,
    ClientOnboardingSession,
    Document,
    MOSApplicationData,
)
from clients.security.encrypted import read_encrypted_json_dict
from clients.services.onboarding_tokens import hash_onboarding_token

CORRUPTED_FERNET_TOKEN = "gAAAA-onboarding-corrupted-token"

urlpatterns = [
    path("", include("clients.urls", namespace="clients")),
    path("i18n/", include("django.conf.urls.i18n")),
    path("accounts/", include("allauth.account.urls")),
]


def _set_raw_json_field(instance: object, field_name: str, raw_value: str) -> None:
    meta = instance._meta  # type: ignore[attr-defined]
    table = connection.ops.quote_name(meta.db_table)
    column = connection.ops.quote_name(meta.get_field(field_name).column)
    pk_column = connection.ops.quote_name(meta.pk.column)
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {table} SET {column} = %s WHERE {pk_column} = %s",
            [raw_value, instance.pk],  # type: ignore[attr-defined]
        )


def _get_raw_json_field(instance: object, field_name: str) -> str:
    meta = instance._meta  # type: ignore[attr-defined]
    table = connection.ops.quote_name(meta.db_table)
    column = connection.ops.quote_name(meta.get_field(field_name).column)
    pk_column = connection.ops.quote_name(meta.pk.column)
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {column} FROM {table} WHERE {pk_column} = %s",
            [instance.pk],  # type: ignore[attr-defined]
        )
        row = cursor.fetchone()
    assert row is not None
    return str(row[0])


@override_settings(LANGUAGE_CODE="en", ROOT_URLCONF=__name__)
class OnboardingEncryptedJSONFailClosedTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="encrypted-onboarding@example.com",
            password="secure-password-123",
        )
        self.client_record = Client.objects.create(
            first_name="Original",
            last_name="Person",
            email="original@example.com",
            phone="+48111000222",
            user=self.user,
            application_purpose="work",
        )
        self.mos_data = MOSApplicationData.objects.get(client=self.client_record)
        self.mos_data.status = "draft"
        self.mos_data.personal_data = {
            "first_name": "Original",
            "last_name": "Person",
            "email": "original@example.com",
            "phone": "+48111000222",
        }
        self.mos_data.save(update_fields=["status", "personal_data", "updated_at"])
        self.token = "encrypted-json-onboarding-token"
        ClientOnboardingSession.objects.create(
            client=self.client_record,
            token_hash=hash_onboarding_token(self.token),
            status="created",
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.force_login(self.user)

    def _corrupt_personal_data(self) -> None:
        _set_raw_json_field(self.mos_data, "personal_data", CORRUPTED_FERNET_TOKEN)

    def test_start_contact_post_preserves_ciphertext_and_client_fields(self) -> None:
        self._corrupt_personal_data()

        response = self.client.post(
            reverse("clients:onboarding_start", kwargs={"token": self.token}),
            {
                "first_name": "Changed",
                "last_name": "Name",
                "email": "changed@example.com",
                "phone": "+48999999999",
            },
        )

        self.assertEqual(response.status_code, 409)
        self.client_record.refresh_from_db()
        self.assertEqual(self.client_record.first_name, "Original")
        self.assertEqual(self.client_record.last_name, "Person")
        self.assertEqual(self.client_record.email, "original@example.com")
        self.assertEqual(self.client_record.phone, "+48111000222")
        self.mos_data.refresh_from_db()
        self.assertEqual(self.mos_data.status, "draft")
        self.assertEqual(
            _get_raw_json_field(self.mos_data, "personal_data"),
            CORRUPTED_FERNET_TOKEN,
        )

    def test_autosave_preflight_prevents_digital_access_partial_write(self) -> None:
        digital_access = ClientDigitalAccess.objects.get(client=self.client_record)
        self.assertFalse(digital_access.has_pesel)
        self._corrupt_personal_data()

        response = self.client.post(
            reverse("clients:onboarding_auto_save", kwargs={"token": self.token}),
            {"has_pesel": "yes", "first_name": "Changed"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["status"], "unavailable")
        digital_access.refresh_from_db()
        self.assertFalse(digital_access.has_pesel)
        self.client_record.refresh_from_db()
        self.assertEqual(self.client_record.first_name, "Original")
        self.assertEqual(
            _get_raw_json_field(self.mos_data, "personal_data"),
            CORRUPTED_FERNET_TOKEN,
        )

    def test_digital_access_rolls_back_when_passport_ocr_source_is_unavailable(self) -> None:
        self.mos_data.personal_data = {}
        self.mos_data.passport_data = {}
        self.mos_data.save(update_fields=["personal_data", "passport_data", "updated_at"])
        document = Document.objects.create(
            client=self.client_record,
            case=self.mos_data.case,
            document_type=DocumentType.PASSPORT.value,
            file="passport.pdf",
            ocr_status="success",
            parsed_data={"first_name": "OCR"},
        )
        _set_raw_json_field(document, "parsed_data", CORRUPTED_FERNET_TOKEN)
        digital_access = ClientDigitalAccess.objects.get(client=self.client_record)
        self.assertFalse(digital_access.has_pesel)

        response = self.client.post(
            reverse("clients:onboarding_digital_access", kwargs={"token": self.token}),
            {"has_pesel": "yes"},
        )

        self.assertEqual(response.status_code, 409)
        digital_access.refresh_from_db()
        self.assertFalse(digital_access.has_pesel)
        self.assertEqual(
            _get_raw_json_field(document, "parsed_data"),
            CORRUPTED_FERNET_TOKEN,
        )

    def test_passport_get_renders_generic_unavailable_state_without_overwrite(self) -> None:
        self._corrupt_personal_data()

        response = self.client.get(
            reverse("clients:onboarding_passport", kwargs={"token": self.token})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Saved form data is temporarily unavailable")
        self.assertEqual(
            _get_raw_json_field(self.mos_data, "personal_data"),
            CORRUPTED_FERNET_TOKEN,
        )

    def test_read_helper_returns_copy_and_logs_metadata_only(self) -> None:
        self._corrupt_personal_data()
        unreadable = MOSApplicationData.objects.get(pk=self.mos_data.pk)

        with self.assertLogs("clients.security.encrypted", level="WARNING") as captured:
            value, unavailable = read_encrypted_json_dict(unreadable, "personal_data")

        self.assertEqual(value, {})
        self.assertTrue(unavailable)
        log_output = "\n".join(captured.output)
        self.assertIn("model=clients.MOSApplicationData", log_output)
        self.assertIn(f"pk={self.mos_data.pk}", log_output)
        self.assertIn("field=personal_data", log_output)
        self.assertNotIn(CORRUPTED_FERNET_TOKEN, log_output)
