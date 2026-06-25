from __future__ import annotations

from django.test import TestCase

from clients.models import Client
from clients.services.mos_eligibility import evaluate_mos_eligibility


class MosEligibilityTests(TestCase):
    def _client(self, **kwargs) -> Client:
        defaults = dict(first_name="A", last_name="B", citizenship="UA")
        defaults.update(kwargs)
        return Client.objects.create(**defaults)

    def _set_stay(self, client: Client, *, in_poland: bool) -> None:
        mos = client.mos_applications.first()
        mos.stay_data = {"is_in_poland": in_poland}
        mos.save(update_fields=["stay_data", "updated_at"])

    def test_family_member_abroad_is_ineligible(self):
        client = self._client(application_purpose="family", family_role="family_spouse")
        self._set_stay(client, in_poland=False)

        result = evaluate_mos_eligibility(client)

        self.assertFalse(result.eligible)
        self.assertTrue(result.has_warnings)

    def test_family_member_in_poland_is_eligible(self):
        client = self._client(application_purpose="family", family_role="family_child")
        self._set_stay(client, in_poland=True)

        result = evaluate_mos_eligibility(client)

        self.assertTrue(result.eligible)
        self.assertFalse(result.has_warnings)

    def test_family_sponsor_abroad_is_not_excluded(self):
        # The sponsor is the principal in Poland; the abroad-exclusion targets the
        # sponsored member, not the sponsor role.
        client = self._client(application_purpose="family", family_role="sponsor")
        self._set_stay(client, in_poland=False)

        self.assertTrue(evaluate_mos_eligibility(client).eligible)

    def test_work_purpose_abroad_is_eligible(self):
        client = self._client(application_purpose="work")
        self._set_stay(client, in_poland=False)

        self.assertTrue(evaluate_mos_eligibility(client).eligible)

    def test_unknown_residence_is_eligible_by_default(self):
        client = self._client(application_purpose="family", family_role="family_spouse")
        # stay_data has no is_in_poland key -> we do not assume abroad.

        self.assertTrue(evaluate_mos_eligibility(client).eligible)
