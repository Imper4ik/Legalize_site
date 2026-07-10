"""Negative HTTP tests for access control and IDOR.

These assert behaviour over real GET/POST requests, not just template button
visibility: a client cannot reach staff endpoints or another client's document,
and staff have office-wide access.
"""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clients.constants import DocumentType
from clients.models import Client, ClientOnboardingSession, Document
from clients.services.onboarding_tokens import hash_onboarding_token
from clients.testing.factories import create_test_document, create_test_user

User = get_user_model()


class RbacIdorHttpTests(TestCase):
    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")

        self.user_a = User.objects.create_user(email="client-a@example.test", password="pw-a-123456")
        self.client_a = Client.objects.create(
            first_name="Alice", last_name="A", email="", phone="", user=self.user_a,
            application_purpose="work", language="ru",
        )
        self.token_a = "portal-token-a"
        ClientOnboardingSession.objects.create(
            client=self.client_a, token_hash=hash_onboarding_token(self.token_a),
            status="created", expires_at=timezone.now() + timedelta(days=7),
        )
        self.doc_a = create_test_document(
            self.client_a, case=self.client_a.cases.first(),
            doc_type=DocumentType.EMPLOYMENT_CONTRACT.value,
        )

        self.user_b = User.objects.create_user(email="client-b@example.test", password="pw-b-123456")
        self.client_b = Client.objects.create(
            first_name="Bob", last_name="B", email="", phone="", user=self.user_b,
            application_purpose="work", language="ru",
        )
        self.doc_b = create_test_document(
            self.client_b, case=self.client_b.cases.first(),
            doc_type=DocumentType.EMPLOYMENT_CONTRACT.value,
        )

    # --- Client cannot reach staff endpoints ---

    def test_non_staff_cannot_download_document(self) -> None:
        self.client.force_login(self.user_a)
        # Even their own document is not served through the staff endpoint.
        resp = self.client.get(reverse("clients:document_download", kwargs={"doc_id": self.doc_a.id}))
        self.assertIn(resp.status_code, (302, 403))

    def test_non_staff_cannot_open_client_detail(self) -> None:
        self.client.force_login(self.user_a)
        resp = self.client.get(reverse("clients:client_detail", kwargs={"pk": self.client_a.id}))
        self.assertIn(resp.status_code, (302, 403))
        if resp.status_code == 302:
            # Must bounce to login, never to the (case) data page.
            self.assertIn("login", resp.headers.get("Location", "").lower())

    def test_non_staff_cannot_post_add_document(self) -> None:
        self.client.force_login(self.user_a)
        before = Document.objects.filter(client=self.client_a).count()
        resp = self.client.post(
            reverse(
                "clients:add_document",
                kwargs={"client_id": self.client_a.id, "doc_type": DocumentType.EMPLOYMENT_CONTRACT.value},
            ),
            data={},
        )
        self.assertIn(resp.status_code, (302, 403))
        self.assertEqual(Document.objects.filter(client=self.client_a).count(), before)

    # --- IDOR: one client cannot reach another's document ---

    def test_portal_cannot_preview_another_clients_document(self) -> None:
        self.client.force_login(self.user_a)
        resp = self.client.get(
            reverse(
                "clients:onboarding_document_preview",
                kwargs={"token": self.token_a, "doc_id": self.doc_b.id},
            )
        )
        self.assertIn(resp.status_code, (403, 404))

    def test_portal_can_preview_own_document(self) -> None:
        self.client.force_login(self.user_a)
        resp = self.client.get(
            reverse(
                "clients:onboarding_document_preview",
                kwargs={"token": self.token_a, "doc_id": self.doc_a.id},
            )
        )
        self.assertEqual(resp.status_code, 200)

    # --- Staff have office-wide access ---

    def test_staff_can_download_any_clients_document(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("clients:document_download", kwargs={"doc_id": self.doc_b.id}))
        self.assertEqual(resp.status_code, 200)

    def test_staff_can_open_any_client_detail(self) -> None:
        self.client.force_login(self.staff)
        # client_detail canonicalises to the case-scoped page; follow the
        # redirect and assert staff reach the data (200), not a login bounce.
        resp = self.client.get(
            reverse("clients:client_detail", kwargs={"pk": self.client_b.id}), follow=True
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("login", resp.request["PATH_INFO"].lower())
