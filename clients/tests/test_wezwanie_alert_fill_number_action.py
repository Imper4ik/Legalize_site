"""The "wezwanie без номера дела" risk tells staff to fill the case number
manually, so it must offer a direct action to the case edit form (where the
authority case number is entered), not only "open document" / "ask client".
"""
from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from django.utils.translation import override

from clients.constants import DocumentType
from clients.testing.factories import create_test_client, create_test_document, create_test_user

# Alert titles are stored as Russian source strings (msgids). Pin the active
# language to Russian so str() of the lazy titles matches the source, regardless
# of which compiled catalogs (pl/en) are present in the environment.
WEZWANIE_TITLE = "Есть wezwanie без номера дела"


class WezwanieFillNumberActionTests(TestCase):
    def test_wezwanie_alert_links_to_case_edit(self) -> None:
        staff = create_test_user(role="Staff")  # noqa: F841 - ensures roles exist
        client = create_test_client(first_name="Wez", last_name="NoNumber")
        case = client.cases.get()
        # No authority number on the case; a wezwanie is uploaded.
        self.assertEqual(case.authority_case_number, "")
        create_test_document(client, case=case, doc_type=DocumentType.WEZWANIE.value)

        with override("ru"):
            alerts = client.get_health_alerts()
            wezwanie = next(
                (a for a in alerts if str(a["title"]) == WEZWANIE_TITLE),
                None,
            )
            self.assertIsNotNone(wezwanie)

            edit_url = reverse("clients:case_edit", kwargs={"pk": case.pk})
            urls = [action.get("url") for action in wezwanie.get("actions", [])]
            self.assertIn(edit_url, urls)

    def test_multi_case_client_gets_fill_action_per_wezwanie_case(self) -> None:
        from clients.services.cases import create_case_for_client

        staff = create_test_user(role="Staff")
        client = create_test_client(first_name="Multi", last_name="Wez")
        case_a = client.cases.get()
        case_b = create_case_for_client(client=client, actor=staff)
        # A wezwanie in each case (neither case has an authority number).
        create_test_document(client, case=case_a, doc_type=DocumentType.WEZWANIE.value)
        create_test_document(client, case=case_b, doc_type=DocumentType.WEZWANIE.value)

        with override("ru"):
            alerts = client.get_health_alerts()
            wezwanie = next(
                (a for a in alerts if str(a["title"]) == WEZWANIE_TITLE),
                None,
            )
            self.assertIsNotNone(wezwanie)
            urls = [action.get("url") for action in wezwanie.get("actions", [])]
            # The fill action exists for BOTH cases, not just one.
            self.assertIn(reverse("clients:case_edit", kwargs={"pk": case_a.pk}), urls)
            self.assertIn(reverse("clients:case_edit", kwargs={"pk": case_b.pk}), urls)
