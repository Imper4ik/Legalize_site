"""spec §5: generate_onboarding_link works in two explicit modes.

- A client with a single active case (or an explicitly chosen case) gets a
  case_link session bound to that case.
- A client with several active cases gets a client_portal session (case=None);
  the case is never silently picked, and the call must not error.
"""
from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from clients.models import ClientOnboardingSession
from clients.services.cases import create_case_for_client
from clients.services.onboarding_tokens import hash_onboarding_token
from clients.testing.factories import (
    TEST_USER_CREDENTIAL,
    create_test_client,
    create_test_user,
)


class GenerateOnboardingLinkModeTests(TestCase):
    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.http = self.client
        self.http.login(email=self.staff.email, password=TEST_USER_CREDENTIAL)

    def _generate(self, client, **post):
        resp = self.http.post(
            reverse("clients:generate_onboarding_link", kwargs={"client_id": client.pk}),
            post,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        token = resp.json()["link"].rstrip("/").split("/")[-1]
        return ClientOnboardingSession.objects.get(token_hash=hash_onboarding_token(token))

    def test_single_case_client_gets_case_link(self) -> None:
        client = create_test_client(first_name="Solo", last_name="Case")
        case = client.cases.get()
        session = self._generate(client)
        self.assertEqual(session.scope, "case_link")
        self.assertEqual(session.case_id, case.id)

    def test_multi_case_client_gets_client_portal(self) -> None:
        client = create_test_client(first_name="Multi", last_name="Case")
        create_case_for_client(client=client, actor=self.staff)
        session = self._generate(client)
        # No case is silently picked for an ambiguous client.
        self.assertEqual(session.scope, "client_portal")
        self.assertIsNone(session.case_id)

    def test_explicit_case_uuid_pins_the_case_link(self) -> None:
        client = create_test_client(first_name="Pick", last_name="Case")
        case_a = client.cases.get()
        case_b = create_case_for_client(client=client, actor=self.staff)
        session = self._generate(client, case_uuid=str(case_b.uuid))
        self.assertEqual(session.scope, "case_link")
        self.assertEqual(session.case_id, case_b.id)
        self.assertNotEqual(session.case_id, case_a.id)
