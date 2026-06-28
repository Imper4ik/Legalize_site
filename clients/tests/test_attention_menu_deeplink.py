"""The "События клиентов" menu leads to the fix: a single matching client links
straight to that client's documents tab; several clients fall back to the
filtered list.
"""
from __future__ import annotations

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from clients.models import Client, Document
from clients.testing.factories import TEST_USER_CREDENTIAL, create_test_user


class AttentionMenuDeepLinkTests(TestCase):
    def setUp(self) -> None:
        # The notifications context processor caches by user pk; pks reset between
        # rolled-back tests while locmem cache persists, so clear it.
        cache.clear()
        self.staff = create_test_user(role="Admin")
        self.client.login(email=self.staff.email, password=TEST_USER_CREDENTIAL)

    def _unverified_client(self, email: str) -> Client:
        client = Client.objects.create(first_name="Unv", last_name="Doc", email=email)
        Document.objects.create(
            client=client,
            document_type="passport",
            file=SimpleUploadedFile(f"{email}.pdf", b"x", content_type="application/pdf"),
            verified=False,
        )
        return client

    def test_single_client_links_to_the_fix(self) -> None:
        client = self._unverified_client("one@example.com")
        resp = self.client.get(reverse("clients:client_list"))
        deep = reverse("clients:client_detail", kwargs={"pk": client.pk}) + "?view=person#documentAccordion"
        self.assertContains(resp, deep)
        # And that destination renders (person view, no redirect).
        self.assertEqual(
            self.client.get(
                reverse("clients:client_detail", kwargs={"pk": client.pk}), {"view": "person"}
            ).status_code,
            200,
        )

    def test_several_clients_fall_back_to_filtered_list(self) -> None:
        self._unverified_client("a@example.com")
        self._unverified_client("b@example.com")
        list_url = reverse("clients:client_list")
        resp = self.client.get(list_url)
        self.assertContains(resp, f"{list_url}?attention=unverified_documents")
        self.assertEqual(resp.context["attention_counts"]["unverified_documents"], 2)
