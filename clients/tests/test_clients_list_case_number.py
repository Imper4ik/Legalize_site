"""The clients list must show the same case number the case detail shows:
authority → legacy → "—". It must never display "—" while the case actually
carries a (legacy) number, and a legacy-only number is flagged as such.
"""
from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from clients.testing.factories import (
    TEST_USER_CREDENTIAL,
    create_test_client,
    create_test_user,
)


class ClientsListCaseNumberTests(TestCase):
    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client.login(email=self.staff.email, password=TEST_USER_CREDENTIAL)

    def _get_list(self):
        return self.client.get(reverse("clients:client_list"))

    def test_authority_number_is_shown(self) -> None:
        client = create_test_client(first_name="Auth", last_name="Number")
        case = client.cases.get()
        case.authority_case_number = "WSC-II-P.6151.1.2026"
        case.save(update_fields=["authority_case_number"])

        resp = self._get_list()
        self.assertContains(resp, "WSC-II-P.6151.1.2026")

    def test_legacy_number_is_shown_and_flagged(self) -> None:
        client = create_test_client(first_name="Legacy", last_name="Number")
        case = client.cases.get()
        case.authority_case_number = ""
        case.legacy_case_number = "WSC-II-P.6151.138285.2025"
        case.save(update_fields=["authority_case_number", "legacy_case_number"])

        from django.utils import translation

        # Request the Russian locale explicitly: the legacy-number tooltip is
        # now translated, so the default (Polish) page no longer contains the
        # Russian source string.
        with translation.override("ru"):
            resp = self._get_list()
        # The legacy number is visible (not "—") ...
        self.assertContains(resp, "WSC-II-P.6151.138285.2025")
        # ... and marked as coming from the previous card.
        self.assertContains(resp, "предыдущей карточки")

    def test_unnumbered_case_shows_dash(self) -> None:
        create_test_client(first_name="No", last_name="Number")
        resp = self._get_list()
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "—")
