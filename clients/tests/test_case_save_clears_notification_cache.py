"""Entering the case number must refresh the navbar "События клиентов" counts
immediately, not after the cache TTL: a Case save clears the cache.
"""
from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from clients.constants import DocumentType
from clients.testing.factories import (
    TEST_USER_CREDENTIAL,
    create_test_client,
    create_test_document,
    create_test_user,
)


class CaseSaveClearsNotificationCacheTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.staff = create_test_user(role="Admin")
        self.client.login(email=self.staff.email, password=TEST_USER_CREDENTIAL)

    def test_entering_case_number_drops_the_wezwanie_count(self) -> None:
        client = create_test_client(first_name="Nav", last_name="Refresh")
        case = client.cases.get()
        create_test_document(client, case=case, doc_type=DocumentType.WEZWANIE.value)

        first = self.client.get(reverse("clients:client_list"))
        self.assertEqual(first.context["attention_counts"]["wezwanie_missing_case"], 1)

        # Enter the authority number — the Case post_save signal clears the cache.
        case.authority_case_number = "WSC-II-P.6151.7.2026"
        case.save(update_fields=["authority_case_number", "authority_case_number_hash"])

        second = self.client.get(reverse("clients:client_list"))
        self.assertEqual(second.context["attention_counts"]["wezwanie_missing_case"], 0)
