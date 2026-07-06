"""RODO art. 17: subject-initiated erasure requests are fulfilled by
anonymizing the client, with an auditable request -> fulfilment trail.
"""
from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from clients.models import Client
from clients.services.anonymization import anonymize_client, is_anonymized
from clients.testing.factories import create_test_client


class ProcessErasureRequestsCommandTests(TestCase):
    def setUp(self) -> None:
        self.requested = create_test_client(first_name="Erasure", last_name="Wanted")
        self.requested.erasure_requested_at = timezone.now()
        self.requested.save(update_fields=["erasure_requested_at"])
        self.untouched = create_test_client(first_name="Keep", last_name="Me")

    def test_command_anonymizes_only_requested_clients(self) -> None:
        call_command("process_erasure_requests")

        requested = Client.all_objects.get(pk=self.requested.pk)
        self.assertTrue(is_anonymized(requested))
        self.assertIsNotNone(requested.erasure_fulfilled_at)

        untouched = Client.all_objects.get(pk=self.untouched.pk)
        self.assertFalse(is_anonymized(untouched))
        self.assertEqual(untouched.first_name, "Keep")

    def test_dry_run_changes_nothing_and_prints_no_pii(self) -> None:
        out = StringIO()
        call_command("process_erasure_requests", "--dry-run", stdout=out)
        output = out.getvalue()

        self.assertNotIn("Erasure", output)
        self.assertIn(str(self.requested.id), output)
        self.assertFalse(is_anonymized(Client.all_objects.get(pk=self.requested.pk)))

    def test_is_idempotent(self) -> None:
        call_command("process_erasure_requests")
        first = Client.all_objects.get(pk=self.requested.pk).erasure_fulfilled_at
        # A second run finds nothing pending (already fulfilled) and does not
        # re-stamp or re-anonymize.
        call_command("process_erasure_requests")
        second = Client.all_objects.get(pk=self.requested.pk).erasure_fulfilled_at
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
