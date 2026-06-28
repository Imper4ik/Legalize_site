"""Two risk-clearing rules:

- the "legal stay expiring" risk disappears once the case is submitted to the
  urząd (the stamp legalises the stay);
- the "wezwanie без номера дела" risk clears once the authority number is entered
  on that wezwanie's case.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.test import TestCase

from clients.constants import DocumentType
from clients.models import Client
from clients.services.attention import apply_client_attention_filter
from clients.testing.factories import create_test_client, create_test_document, create_test_user

LEGAL_STAY_TITLES = {"Основание пребывания скоро истекает", "Основание пребывания уже истекло"}


class LegalStaySubmittedTests(TestCase):
    def setUp(self) -> None:
        self.client_obj = create_test_client(first_name="Stay", last_name="Submit")
        self.case = self.client_obj.cases.get()
        self.case.workflow_stage = "document_collection"
        self.case.save(update_fields=["workflow_stage"])
        # Stay basis expiring within 30 days → the risk is relevant.
        self.client_obj.legal_basis_end_date = date.today() + timedelta(days=10)
        self.client_obj.save(update_fields=["legal_basis_end_date"])

    def _alert_titles(self):
        return {str(a["title"]) for a in self.client_obj.get_health_alerts()}

    def test_legal_stay_risk_shown_before_submission(self) -> None:
        self.assertTrue(self._alert_titles() & LEGAL_STAY_TITLES)
        # And the client appears under the navbar legal-stay attention filter.
        flagged = apply_client_attention_filter(Client.objects.all(), "legal_stay")
        self.assertIn(self.client_obj.pk, list(flagged.values_list("pk", flat=True)))

    def test_legal_stay_risk_removed_after_submission(self) -> None:
        self.case.submission_date = date.today()
        self.case.save(update_fields=["submission_date"])

        self.assertFalse(self._alert_titles() & LEGAL_STAY_TITLES)
        # The automatic check turns into a positive "submitted" status.
        checks = self.client_obj.get_automatic_checks()
        stay = next(c for c in checks if str(c["label"]) == "Легальность пребывания")
        self.assertEqual(stay["status"], "success")
        self.assertIn("подано", str(stay["message"]).lower())
        # And it drops out of the navbar legal-stay filter.
        flagged = apply_client_attention_filter(Client.objects.all(), "legal_stay")
        self.assertNotIn(self.client_obj.pk, list(flagged.values_list("pk", flat=True)))


class WezwanieNumberClearsTests(TestCase):
    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(first_name="Wez", last_name="Clear")
        self.case = self.client_obj.cases.get()
        create_test_document(self.client_obj, case=self.case, doc_type=DocumentType.WEZWANIE.value)

    def _has_wezwanie_alert(self) -> bool:
        return any(
            str(a["title"]) == "Есть wezwanie без номера дела"
            for a in self.client_obj.get_health_alerts()
        )

    def test_alert_shown_without_number(self) -> None:
        self.assertEqual(self.case.authority_case_number, "")
        self.assertTrue(self._has_wezwanie_alert())

    def test_alert_cleared_once_number_entered(self) -> None:
        self.case.authority_case_number = "WSC-II-P.6151.5.2026"
        self.case.save(update_fields=["authority_case_number"])
        self.assertFalse(self._has_wezwanie_alert())
        # And the navbar wezwanie filter no longer flags the client.
        flagged = apply_client_attention_filter(Client.objects.all(), "wezwanie_missing_case")
        self.assertNotIn(self.client_obj.pk, list(flagged.values_list("pk", flat=True)))
