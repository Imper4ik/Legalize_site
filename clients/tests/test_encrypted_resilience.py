from __future__ import annotations

import zipfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from clients.models import Client, ClientOnboardingSession, MOSApplicationData
from clients.security.encrypted import ENCRYPTED_VALUE_UNAVAILABLE, safe_encrypted_attr
from clients.services.export import generate_client_zip
from clients.services.onboarding_tokens import hash_onboarding_token
from clients.services.roles import ensure_predefined_roles


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

    def _login_staff(self) -> None:
        ensure_predefined_roles()
        user_model = get_user_model()
        staff = user_model.objects.create_user(
            email=f"staff-{Client.objects.count()}@example.com",
            password="securepassword",
            is_staff=True,
        )
        staff.groups.add(Group.objects.get(name="Staff"))
        self.client.login(email=staff.email, password="securepassword")

    def test_corrupted_case_number_does_not_break_client_list(self):
        self._login_staff()
        client = Client.objects.create(first_name="List", last_name="Client", case_number="SECRET-CASE")
        _corrupt_client_field(client, "case_number")

        response = self.client.get(reverse("clients:client_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ENCRYPTED_VALUE_UNAVAILABLE)
        self.assertNotContains(response, "SECRET-CASE")

    def test_corrupted_case_number_does_not_break_client_detail(self):
        self._login_staff()
        client = Client.objects.create(first_name="Detail", last_name="Client", case_number="SECRET-CASE")
        _corrupt_client_field(client, "case_number")

        response = self.client.get(reverse("clients:client_detail", kwargs={"pk": client.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ENCRYPTED_VALUE_UNAVAILABLE)
        self.assertNotContains(response, "SECRET-CASE")

    def test_corrupted_passport_num_does_not_break_client_list_or_detail(self):
        self._login_staff()
        client = Client.objects.create(first_name="Passport", last_name="Client", passport_num="PP123456")
        _corrupt_client_field(client, "passport_num")

        list_response = self.client.get(reverse("clients:client_list"))
        detail_response = self.client.get(reverse("clients:client_detail", kwargs={"pk": client.pk}))

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertNotContains(list_response, "PP123456")
        self.assertNotContains(detail_response, "PP123456")

    def test_corrupted_sponsor_encrypted_fields_do_not_break_member_list_or_detail(self):
        self._login_staff()
        sponsor = Client.objects.create(
            first_name="Sponsor",
            last_name="Encrypted",
            case_number="SPONSOR-SECRET",
            passport_num="SPONSORPASS",
        )
        member = Client.objects.create(first_name="Member", last_name="Client", sponsor_client=sponsor)
        _corrupt_client_field(sponsor, "case_number")
        _corrupt_client_field(sponsor, "passport_num")

        list_response = self.client.get(reverse("clients:client_list"))
        detail_response = self.client.get(reverse("clients:client_detail", kwargs={"pk": member.pk}))

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertNotContains(list_response, "SPONSOR-SECRET")
        self.assertNotContains(detail_response, "SPONSOR-SECRET")
        self.assertNotContains(list_response, "SPONSORPASS")
        self.assertNotContains(detail_response, "SPONSORPASS")

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
        client = Client.objects.create(first_name="Onboard", last_name="Client", passport_num="PP123456")
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
