"""The client-level payment/task forms must let staff attach the record to a
concrete case: a hidden case for a single-case client, an explicit picker when
the client has several active cases (spec §6).
"""
from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from clients.services.cases import create_case_for_client
from clients.testing.factories import (
    TEST_USER_CREDENTIAL,
    create_test_client,
    create_test_user,
)


class ClientDetailCasePickerTests(TestCase):
    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client.login(email=self.staff.email, password=TEST_USER_CREDENTIAL)

    def _detail(self, client):
        # ?view=person keeps the client (person) view; without it a single-case
        # client is redirected straight to its case detail.
        return self.client.get(
            reverse("clients:client_detail", kwargs={"pk": client.pk}) + "?view=person"
        )

    def test_single_case_uses_hidden_case_field(self) -> None:
        client = create_test_client(first_name="Solo", last_name="Detail")
        case = client.cases.get()
        resp = self._detail(client)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('name="case_uuid"', body)
        self.assertIn(str(case.uuid), body)
        # No visible picker dropdown for a single case.
        self.assertNotIn('<option value="" selected disabled>Выберите дело', body)

    def test_multi_case_renders_picker(self) -> None:
        client = create_test_client(first_name="Multi", last_name="Detail")
        case_a = client.cases.get()
        case_b = create_case_for_client(client=client, actor=self.staff)
        resp = self._detail(client)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('name="case_uuid"', body)
        self.assertIn("Выберите дело", body)
        self.assertIn(str(case_a.uuid), body)
        self.assertIn(str(case_b.uuid), body)
