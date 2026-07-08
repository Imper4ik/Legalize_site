"""Legacy process-field transfer in Client.objects.create() targets the single
primary case deterministically, and refuses to guess when a client already has
several cases (never writes one process's data onto an arbitrary case).
"""
from __future__ import annotations

from datetime import date

from django.test import TestCase

from clients.models import Case, Client
from clients.models.client import _apply_case_process_kwargs
from clients.testing.factories import create_test_client


class CaseProcessKwargsTransferTests(TestCase):
    def test_create_applies_process_fields_to_the_single_case(self) -> None:
        client = Client.objects.create(
            first_name="Proc",
            last_name="Fields",
            fingerprints_location="Office 7",
            fingerprints_date=date(2026, 3, 1),
        )
        case = client.cases.get()
        self.assertEqual(case.fingerprints_location, "Office 7")
        self.assertEqual(case.fingerprints_date, date(2026, 3, 1))

    def test_multi_case_client_is_not_guessed(self) -> None:
        client = create_test_client(first_name="Multi", last_name="Case")
        first_case = client.cases.get()
        second_case = Case.objects.create(client=client, workflow_stage="new_client")
        self.assertEqual(client.cases.count(), 2)

        with self.assertLogs("clients.models.client", level="WARNING") as logs:
            _apply_case_process_kwargs(client, {"fingerprints_location": "Should not land"})

        self.assertTrue(any("expected a single case" in m for m in logs.output))
        # Neither case was written to.
        first_case.refresh_from_db()
        second_case.refresh_from_db()
        self.assertEqual(first_case.fingerprints_location, "")
        self.assertEqual(second_case.fingerprints_location, "")
