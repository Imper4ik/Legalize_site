"""RODO art. 17: subject-initiated erasure requests are fulfilled by
anonymizing the client, with an auditable request -> fulfilment trail.
"""
from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from clients.models import Client
from clients.services.anonymization import anonymize_client, is_anonymized
from clients.services.erasure import approve_erasure, place_legal_hold, request_erasure
from clients.testing.factories import create_test_client


class ProcessErasureRequestsCommandTests(TestCase):
    def setUp(self) -> None:
        # Approved request → the command should fulfil it.
        self.approved = create_test_client(first_name="Erasure", last_name="Wanted")
        request_erasure(self.approved)
        approve_erasure(self.approved, actor=None, reason="verified")
        # Requested but not yet approved → must be left alone.
        self.requested_only = create_test_client(first_name="Pending", last_name="Review")
        request_erasure(self.requested_only)
        # Approved but under legal hold → must be left alone.
        self.held = create_test_client(first_name="Held", last_name="Case")
        request_erasure(self.held)
        approve_erasure(self.held, actor=None, reason="verified")
        place_legal_hold(self.held, reason="ongoing case")
        # No request at all.
        self.untouched = create_test_client(first_name="Keep", last_name="Me")

    def test_command_fulfils_only_approved_non_held(self) -> None:
        call_command("process_erasure_requests")

        approved = Client.all_objects.get(pk=self.approved.pk)
        self.assertTrue(is_anonymized(approved))
        self.assertIsNotNone(approved.erasure_fulfilled_at)
        self.assertEqual(approved.erasure_status, Client.ErasureStatus.FULFILLED)

        # Requested-only, held, and untouched are all left intact.
        for pk, name in (
            (self.requested_only.pk, "Pending"),
            (self.held.pk, "Held"),
            (self.untouched.pk, "Keep"),
        ):
            client = Client.all_objects.get(pk=pk)
            self.assertFalse(is_anonymized(client))
            self.assertEqual(client.first_name, name)

    def test_dry_run_changes_nothing_and_prints_no_pii(self) -> None:
        out = StringIO()
        call_command("process_erasure_requests", "--dry-run", stdout=out)
        output = out.getvalue()

        self.assertNotIn("Erasure", output)
        self.assertIn(str(self.approved.id), output)
        self.assertFalse(is_anonymized(Client.all_objects.get(pk=self.approved.pk)))

    def test_is_idempotent(self) -> None:
        call_command("process_erasure_requests")
        first = Client.all_objects.get(pk=self.approved.pk).erasure_fulfilled_at
        # A second run finds nothing approved-and-pending and does not re-stamp.
        call_command("process_erasure_requests")
        second = Client.all_objects.get(pk=self.approved.pk).erasure_fulfilled_at
        self.assertEqual(first, second)


class AnonymizeClientServiceTests(TestCase):
    def test_skips_already_anonymized_client(self) -> None:
        client = create_test_client(first_name="Once", last_name="Only")
        docs_first = anonymize_client(client)
        name_after_first = Client.all_objects.get(pk=client.pk).first_name

        # Re-running is a no-op for the PII and returns zero deleted documents.
        docs_second = anonymize_client(Client.all_objects.get(pk=client.pk))
        self.assertEqual(docs_second, 0)
        self.assertEqual(
            Client.all_objects.get(pk=client.pk).first_name, name_after_first
        )
        self.assertEqual(docs_first, 0)  # test client has no documents
