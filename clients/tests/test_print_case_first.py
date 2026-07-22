"""The printed mazowiecki application must reflect the case, not client mirrors.

``Client.application_purpose`` / ``Client.basis_of_stay`` are legacy mirrors
that are copied onto the first case and never synced back, so after staff
change the case they diverge permanently. The print form used to read the
stale mirrors, putting a wrong "pobyt czasowy" checkbox and "inne" text on the
official paper form.
"""
from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from clients.models import Case
from clients.services.cases import create_case_for_client
from clients.testing.factories import TEST_USER_CREDENTIAL, create_test_client, create_test_user


class MazowieckiPrintCaseFirstTests(TestCase):
    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client.login(email=self.staff.email, password=TEST_USER_CREDENTIAL)
        self.client_obj = create_test_client(purpose="work")
        self.case = self.client_obj.cases.get()

    def _print_context(self) -> dict:
        response = self.client.get(
            reverse(
                "clients:client_document_print",
                kwargs={"pk": self.client_obj.pk, "doc_type": "mazowiecki_application"},
            )
        )
        self.assertEqual(response.status_code, 200)
        return response.context

    def test_checkbox_and_inne_follow_the_case_after_divergence(self) -> None:
        # Staff re-scope the case; the client mirror still says "work".
        Case.all_objects.filter(pk=self.case.pk).update(
            application_purpose="humanitarian", basis_of_stay="wiza krajowa D"
        )
        self.client_obj.basis_of_stay = "stale mirror value"
        self.client_obj.save(update_fields=["basis_of_stay"])

        context = self._print_context()

        self.assertFalse(context["check_pobyt_czasowy"])
        self.assertEqual(context["other_text"], "wiza krajowa D")

    def test_case_purpose_drives_pobyt_czasowy_checkbox(self) -> None:
        context = self._print_context()
        self.assertTrue(context["check_pobyt_czasowy"])

    def test_falls_back_to_client_mirror_without_single_active_case(self) -> None:
        # A second active case makes the case ambiguous; the view then uses the
        # legacy client-level values instead of guessing between cases.
        create_case_for_client(
            client=self.client_obj, actor=self.staff, application_purpose="study"
        )
        self.client_obj.basis_of_stay = "client-level basis"
        self.client_obj.save(update_fields=["basis_of_stay"])

        context = self._print_context()

        self.assertTrue(context["check_pobyt_czasowy"])  # client mirror: work
        self.assertEqual(context["other_text"], "client-level basis")
