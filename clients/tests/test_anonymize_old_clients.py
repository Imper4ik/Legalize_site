"""spec §9: anonymisation clears case-level numbers and never touches the
removed Client.case_number field, and the dry run prints no PII.
"""
from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from clients.models import Case, Client
from clients.testing.factories import create_test_client


class AnonymizeOldClientsTests(TestCase):
    def setUp(self) -> None:
        self.client_obj = create_test_client(first_name="Zlatan", last_name="Piison")
        self.case = self.client_obj.cases.get()
        self.case.authority_case_number = "WSC-II-P.6151.999.2019"
        self.case.legacy_case_number = "OLD-1"
        self.case.fingerprints_location = "Secret office"
        self.case.save()
        # Backdate creation past the default 5-year cutoff (auto_now_add bypass).
        Client.all_objects.filter(pk=self.client_obj.pk).update(
            created_at=timezone.now() - timedelta(days=6 * 365)
        )

    def test_anonymisation_clears_client_and_case_pii(self) -> None:
        call_command("anonymize_old_clients")

        client = Client.all_objects.get(pk=self.client_obj.pk)
        self.assertTrue(client.first_name.startswith("Anonymized"))
        self.assertEqual(client.last_name, "User")
        self.assertNotIn("Zlatan", client.first_name)

        case = Case.all_objects.get(pk=self.case.pk)
        self.assertEqual(case.authority_case_number, "")
        self.assertEqual(case.legacy_case_number, "")
        self.assertEqual(case.fingerprints_location, "")
        # The removed Client.case_number is never referenced.
        self.assertFalse(hasattr(Client, "case_number"))

    def test_dry_run_prints_no_pii(self) -> None:
        out = StringIO()
        call_command("anonymize_old_clients", "--dry-run", stdout=out)
        output = out.getvalue()
        self.assertNotIn("Zlatan", output)
        self.assertNotIn("Piison", output)
        # The client is still listed by id only.
        self.assertIn(str(self.client_obj.id), output)
        # And nothing was actually changed.
        self.assertEqual(
            Client.all_objects.get(pk=self.client_obj.pk).first_name, "Zlatan"
        )
