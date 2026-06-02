from __future__ import annotations

import zipfile
from datetime import timedelta

from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from clients.models import Client, ClientOnboardingSession, MOSApplicationData
from clients.security.encrypted import ENCRYPTED_VALUE_UNAVAILABLE, safe_encrypted_attr
from clients.services.export import generate_client_zip
from clients.services.onboarding_tokens import hash_onboarding_token


CORRUPTED_FERNET_TOKEN = "gAAAA-corrupted-token"


def _corrupt_client_field(client: Client, field_name: str) -> None:
    table = Client._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {table} SET {field_name} = %s WHERE id = %s",
            [CORRUPTED_FERNET_TOKEN, client.pk],
        )


@override_settings(LANGUAGE_CODE="en")
class EncryptedFieldResilienceTests(TestCase):
    def test_safe_encrypted_attr_returns_placeholder_and_logs_metadata_only(self):
        client = Client.objects.create(first_name="Safe", last_name="Client", case_number="SECRET-CASE")
        _corrupt_client_field(client, "case_number")
        client = Client.objects.defer("case_number").get(pk=client.pk)

        with self.assertLogs("clients.security.encrypted", level="WARNING") as captured:
            value = safe_encrypted_attr(client, "case_number")

        self.assertEqual(value, ENCRYPTED_VALUE_UNAVAILABLE)
        log_output = "\n".join(captured.output)
        self.assertIn("model=clients.Client", log_output)
        self.assertIn(f"pk={client.pk}", log_output)
        self.assertIn("field=case_number", log_output)
        self.assertNotIn(CORRUPTED_FERNET_TOKEN, log_output)
        self.assertNotIn("SECRET-CASE", log_output)

    def test_corrupted_case_number_does_not_break_zip_export(self):
        client = Client.objects.create(first_name="Export", last_name="Client", case_number="SECRET-CASE")
        _corrupt_client_field(client, "case_number")
        client = Client.objects.defer("case_number", "passport_num").get(pk=client.pk)

        buffer = generate_client_zip(client)

        with zipfile.ZipFile(buffer) as archive:
            summary = archive.read(f"case_{client.pk}/CASE_SUMMARY.txt").decode()
        self.assertIn(ENCRYPTED_VALUE_UNAVAILABLE, summary)
        self.assertNotIn("SECRET-CASE", summary)

    def test_corrupted_passport_num_does_not_break_onboarding_passport(self):
        client = Client.objects.create(first_name="Onboard", last_name="Client", email="onboard@example.com", passport_num="PP123456")
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(email="onboard@example.com", password="password123")
        client.user = user
        client.save()
        self.client.force_login(user)

        token = "onboarding-token"
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hash_onboarding_token(token),
            status="created",
            expires_at=timezone.now() + timedelta(days=7),
        )
        MOSApplicationData.objects.filter(client=client).update(status="draft")
        _corrupt_client_field(client, "passport_num")

        response = self.client.get(reverse("clients:onboarding_passport", kwargs={"token": token}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ENCRYPTED_VALUE_UNAVAILABLE)
        self.assertNotContains(response, "PP123456")
