from __future__ import annotations

import zipfile
from datetime import timedelta

from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from clients.constants import DocumentType
from clients.models import Client, ClientOnboardingSession, Document, MOSApplicationData
from clients.security.encrypted import ENCRYPTED_VALUE_UNAVAILABLE, safe_encrypted_attr
from clients.services.export import generate_client_zip
from clients.services.onboarding_tokens import hash_onboarding_token
from clients.testing.factories import (
    TEST_USER_CREDENTIAL,
    create_test_client,
    create_test_document,
    create_test_user,
)

CORRUPTED_FERNET_TOKEN = "gAAAA-corrupted-token"


def _corrupt_client_field(client: Client, field_name: str) -> None:
    table = Client._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {table} SET {field_name} = %s WHERE id = %s",
            [CORRUPTED_FERNET_TOKEN, client.pk],
        )


def _corrupt_document_parsed_data(document: Document) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {Document._meta.db_table} SET parsed_data = %s WHERE id = %s",
            [CORRUPTED_FERNET_TOKEN, document.pk],
        )


def _raw_document_parsed_data(document: Document) -> str:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT parsed_data FROM {Document._meta.db_table} WHERE id = %s",
            [document.pk],
        )
        row = cursor.fetchone()
    assert row is not None
    return str(row[0])


@override_settings(LANGUAGE_CODE="en")
class EncryptedFieldResilienceTests(TestCase):
    def test_safe_encrypted_attr_returns_placeholder_and_logs_metadata_only(self):
        # The case number lives on the case now (spec §4); corrupt that field.
        from clients.models import Case

        client = Client.objects.create(first_name="Safe", last_name="Client", case_number="SECRET-CASE")
        case = client.cases.get()
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {case._meta.db_table} SET authority_case_number = %s WHERE id = %s",
                [CORRUPTED_FERNET_TOKEN, case.pk],
            )
        case = Case.objects.get(pk=case.pk)

        with self.assertLogs("clients.security.encrypted", level="WARNING") as captured:
            value = safe_encrypted_attr(case, "authority_case_number")

        self.assertEqual(value, ENCRYPTED_VALUE_UNAVAILABLE)
        log_output = "\n".join(captured.output)
        self.assertIn("model=clients.Case", log_output)
        self.assertIn(f"pk={case.pk}", log_output)
        self.assertIn("field=authority_case_number", log_output)
        self.assertNotIn(CORRUPTED_FERNET_TOKEN, log_output)
        self.assertNotIn("SECRET-CASE", log_output)

    def test_corrupted_case_number_does_not_break_zip_export(self):
        # The export now sources the case number from the case (spec section 5),
        # so corrupt the case's authority_case_number rather than the client's
        # legacy field.
        client = Client.objects.create(first_name="Export", last_name="Client")
        case = client.cases.get()
        case.authority_case_number = "SECRET-CASE"
        case.save(update_fields=["authority_case_number"])

        table = case._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET authority_case_number = %s WHERE id = %s",
                [CORRUPTED_FERNET_TOKEN, case.pk],
            )
        client = Client.objects.defer("passport_num").get(pk=client.pk)

        buffer = generate_client_zip(client)

        with zipfile.ZipFile(buffer) as archive:
            summary = archive.read(f"case_{client.pk}/CASE_SUMMARY.txt").decode()
        self.assertIn(ENCRYPTED_VALUE_UNAVAILABLE, summary)
        self.assertNotIn("SECRET-CASE", summary)

    def test_corrupted_passport_num_does_not_break_onboarding_passport(self):
        client = Client.objects.create(
            first_name="Onboard", last_name="Client", email="onboard@example.com", passport_num="PP123456"
        )
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
        self.assertContains(response, "Saved form data is temporarily unavailable")
        self.assertNotContains(response, ENCRYPTED_VALUE_UNAVAILABLE)
        self.assertNotContains(response, "PP123456")

    def test_corrupted_document_json_does_not_break_checklists_or_case_detail(self):
        staff = create_test_user(role="Admin")
        client_obj = create_test_client(purpose="work")
        case = client_obj.cases.get()
        doc_type = DocumentType.ZUS_RCA_OR_INSURANCE.value

        warning_document = create_test_document(
            client_obj,
            case=case,
            doc_type=doc_type,
            verified=True,
            ocr_status="success",
            filename="warning.pdf",
        )
        warning_document.ocr_name_mismatch = False
        warning_document.parsed_data = {"warnings": ["manual review"]}
        warning_document.save(update_fields=["ocr_name_mismatch", "parsed_data"])

        unreadable_document = create_test_document(
            client_obj,
            case=case,
            doc_type=doc_type,
            verified=True,
            ocr_status="success",
            filename="unreadable.pdf",
        )
        unreadable_document.ocr_name_mismatch = False
        unreadable_document.parsed_data = {"warnings": []}
        unreadable_document.save(update_fields=["ocr_name_mismatch", "parsed_data"])
        _corrupt_document_parsed_data(unreadable_document)

        with self.assertLogs("fernet_fields.fields", level="WARNING") as captured:
            case_rows = {row["code"]: row for row in case.get_document_checklist()}
            legacy_rows = {row["code"]: row for row in client_obj.get_document_checklist()}
            self.client.login(email=staff.email, password=TEST_USER_CREDENTIAL)
            response = self.client.get(reverse("clients:case_detail", kwargs={"pk": case.pk}))

        for rows in (case_rows, legacy_rows):
            zus_row = rows[doc_type]
            self.assertTrue(zus_row["has_ocr_warning"])
            self.assertEqual(zus_row["ocr_warning_doc_id"], warning_document.pk)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'data-jump-doc="{warning_document.pk}" data-jump-action="warning"',
            html=False,
        )
        log_output = "\n".join(captured.output)
        self.assertNotIn(CORRUPTED_FERNET_TOKEN, log_output)
        self.assertNotIn(CORRUPTED_FERNET_TOKEN, response.content.decode())

    def test_unreadable_document_json_cannot_be_reviewed_confirmed_or_scrubbed(self):
        staff = create_test_user(role="Admin")
        client_obj = create_test_client(
            purpose="work",
            first_name="Original",
            last_name="Client",
        )
        case = client_obj.cases.get()
        document = create_test_document(
            client_obj,
            case=case,
            doc_type=DocumentType.WEZWANIE.value,
            awaiting_confirmation=True,
            ocr_status="success",
            filename="wezwanie.pdf",
        )
        document.parsed_data = {"case_number": "ORIGINAL"}
        document.save(update_fields=["parsed_data"])
        _corrupt_document_parsed_data(document)
        raw_before = _raw_document_parsed_data(document)

        self.client.login(email=staff.email, password=TEST_USER_CREDENTIAL)
        parsed_url = reverse("clients:get_document_parsed_data", kwargs={"doc_id": document.pk})
        confirm_url = reverse("clients:confirm_wezwanie_parse", kwargs={"doc_id": document.pk})
        with self.assertLogs("fernet_fields.fields", level="WARNING") as captured:
            parsed_response = self.client.get(parsed_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
            confirm_response = self.client.post(
                confirm_url,
                data={"first_name": "Changed", "case_number": "CHANGED"},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            document.refresh_from_db()
            self.assertFalse(document.scrub_parsed_pii())
            document.save(update_fields=["parsed_data"])

        self.assertEqual(parsed_response.status_code, 409)
        self.assertEqual(confirm_response.status_code, 409)
        self.assertIn("error", parsed_response.json())
        self.assertEqual(confirm_response.json()["status"], "error")
        self.assertTrue(document.awaiting_confirmation)
        self.assertEqual(_raw_document_parsed_data(document), raw_before)

        client_obj.refresh_from_db()
        case.refresh_from_db()
        self.assertEqual(client_obj.first_name, "Original")
        self.assertNotEqual(case.authority_case_number, "CHANGED")
        log_output = "\n".join(captured.output)
        self.assertNotIn(CORRUPTED_FERNET_TOKEN, log_output)
        self.assertNotIn(CORRUPTED_FERNET_TOKEN, parsed_response.content.decode())
        self.assertNotIn(CORRUPTED_FERNET_TOKEN, confirm_response.content.decode())
