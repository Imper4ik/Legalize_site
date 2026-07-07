"""RODO art. 17: erasure must be irreversible and cover *every* PII store.

Because the controller holds the Fernet keys, encrypted-at-rest PII left behind
is reversible pseudonymisation, not erasure. These tests pin that anonymisation
purges the client identity fields, PESEL, the MOS questionnaire, PESEL
applications, intake submissions, and email-log PII — not just the name.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.test import TestCase

from clients.models import (
    Client,
    ClientDigitalAccess,
    ClientIntakeSubmission,
    Document,
    EmailLog,
    MOSApplicationData,
    PeselApplication,
)
from clients.services.anonymization import ErasureIncompleteError, anonymize_client
from clients.testing.factories import create_client_user, create_test_client, create_test_document


class AnonymizationCompletenessTests(TestCase):
    def setUp(self) -> None:
        self.client_obj = create_test_client(first_name="Full", last_name="Pii")
        self.case = self.client_obj.cases.get()
        # Direct client PII beyond the name.
        self.client_obj.citizenship = "Ukraine"
        self.client_obj.birth_date = date(1990, 5, 17)
        self.client_obj.passport_num = "AB1234567"
        self.client_obj.employer_phone = "48111222333"
        self.client_obj.notes = "sensitive free-text note"
        self.client_obj.save()

        ClientDigitalAccess.objects.update_or_create(
            client=self.client_obj,
            defaults={"has_pesel": True, "pesel": "90051712345"},
        )
        MOSApplicationData.objects.update_or_create(
            case=self.case,
            defaults={
                "client": self.client_obj,
                "personal_data": {"first_name": "Full", "father_name": "Ivan"},
                "passport_data": {"document_number": "AB1234567"},
            },
        )
        PeselApplication.objects.create(
            client=self.client_obj,
            case=self.case,
            pesel_form_data={"first_name": "Full", "pesel": "90051712345"},
        )
        ClientIntakeSubmission.objects.create(
            created_client=self.client_obj,
            token_hash="hash-intake-1",
            personal_data={"first_name": "Full", "email": "full@example.com"},
        )
        EmailLog.objects.create(
            client=self.client_obj,
            subject="Wezwanie for Full Pii",
            body="Dear Full Pii, your appointment...",
            recipients="full@example.com",
        )
        # One active and one archived (soft-deleted) document — both hold files.
        self.active_doc = create_test_document(self.client_obj, filename="active.pdf")
        self.archived_doc = create_test_document(self.client_obj, filename="archived.pdf")
        self.archived_doc.delete()  # soft delete → archived_at set, excluded from .objects

    def test_all_pii_stores_are_purged(self) -> None:
        anonymize_client(self.client_obj)

        client = Client.all_objects.get(pk=self.client_obj.pk)
        # Client identity fields.
        self.assertEqual(client.citizenship, "")
        self.assertIsNone(client.birth_date)
        self.assertIn(client.passport_num, (None, ""))
        self.assertEqual(client.employer_phone, "")
        self.assertEqual(client.notes, "")

        # Related PII stores are gone.
        self.assertFalse(ClientDigitalAccess.objects.filter(client=client).exists())
        self.assertFalse(MOSApplicationData.objects.filter(client=client).exists())
        self.assertFalse(PeselApplication.objects.filter(client=client).exists())
        self.assertFalse(
            ClientIntakeSubmission.objects.filter(created_client=client).exists()
        )

        # Documents — including the archived one — are hard-deleted.
        self.assertFalse(Document.all_objects.filter(client=client).exists())

        # Email-log PII content wiped, audit shell kept.
        log = EmailLog.objects.get(client=client)
        self.assertEqual(log.body, "")
        self.assertEqual(log.recipients, "")
        self.assertNotIn("Full", log.subject)


class AnonymizationPortalUserTests(TestCase):
    def test_non_staff_portal_user_is_scrubbed_and_unlinked(self) -> None:
        client = create_test_client(first_name="Portal", last_name="User")
        user = create_client_user(email="portal-subject@example.test")
        client.user = user
        client.save(update_fields=["user"])

        anonymize_client(client)

        client.refresh_from_db()
        self.assertIsNone(client.user)  # unlinked
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertNotIn("portal-subject", user.email)
        self.assertNotIn("portal-subject", user.username)

    def test_staff_account_is_never_touched(self) -> None:
        from clients.testing.factories import create_test_user

        client = create_test_client(first_name="Staff", last_name="Linked")
        staff = create_test_user(role="Staff")
        original_email = staff.email
        client.user = staff
        client.save(update_fields=["user"])

        anonymize_client(client)

        staff.refresh_from_db()
        self.assertTrue(staff.is_active)
        self.assertEqual(staff.email, original_email)


class AnonymizationVerificationGateTests(TestCase):
    def test_fulfilled_not_stamped_when_pii_survives(self) -> None:
        client = create_test_client(first_name="Gate", last_name="Keeper")
        create_test_document(client, filename="residual.pdf")

        # Simulate a purge that fails to remove everything.
        with patch(
            "clients.services.anonymization._purge_subject_stores", return_value=0
        ):
            with self.assertRaises(ErasureIncompleteError):
                anonymize_client(client, mark_erasure_fulfilled=True)

        client.refresh_from_db()
        # Transaction rolled back → request stays open, nothing marked fulfilled.
        self.assertIsNone(client.erasure_fulfilled_at)

    def test_fulfilled_stamped_after_complete_erasure(self) -> None:
        client = create_test_client(first_name="Done", last_name="Erased")
        create_test_document(client, filename="gone.pdf")

        anonymize_client(client, mark_erasure_fulfilled=True)

        client.refresh_from_db()
        self.assertIsNotNone(client.erasure_fulfilled_at)
