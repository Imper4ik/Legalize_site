from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client as DjangoClient
from django.test import TestCase
from django.urls import reverse

from clients.models import ClientOnboardingSession
from clients.services.onboarding_tokens import hash_onboarding_token
from clients.testing.e2e_runner import run_e2e_scenarios


class AdminToolsUiTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.superuser = user_model.objects.create_superuser(
            email="admin-tools@example.test",
            password="pass",
        )
        self.browser = DjangoClient()
        self.browser.force_login(self.superuser)

    def test_admin_panel_uses_operational_workbench_layout(self) -> None:
        response = self.browser.get(reverse("clients:admin_panel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ops-shell")
        self.assertContains(response, "ops-risk-grid")
        self.assertContains(response, "Test Center")
        self.assertContains(response, "Demo Center")

    def test_demo_center_uses_demo_workbench_layout(self) -> None:
        response = self.browser.get(reverse("clients:demo_center"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "demo-workbench")
        self.assertContains(response, "Prepare 5-minute demo")
        self.assertContains(response, "demo-route")
        self.assertContains(response, "demo-card")
        self.assertContains(response, "demo-purpose-strip")
        self.assertContains(response, "Open OCR review")
        html = response.content.decode()
        self.assertLess(html.index("</main>"), html.index('id="emailPreviewModal"'))

    def test_test_center_uses_test_workbench_layout(self) -> None:
        response = self.browser.get(reverse("clients:test_center"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "test-workbench")
        self.assertContains(response, "tc-mode-list")
        self.assertContains(response, "tc-mode-card")
        self.assertContains(response, "Smoke")

    def test_test_center_kept_smoke_run_links_to_valid_client_portal(self) -> None:
        test_run = run_e2e_scenarios(mode="smoke", started_by=self.superuser, cleanup=False)
        result = test_run.results.get(scenario_name="smoke.invite_link_resolves_expected_client")
        token = result.related_case_identifier.removeprefix("onboarding:")

        self.assertTrue(token)
        self.assertTrue(
            ClientOnboardingSession.objects.filter(
                client=result.related_client,
                token_hash=hash_onboarding_token(token),
            )
            .exclude(status__in=["revoked", "expired"])
            .exists()
        )

        response = self.browser.get(f"{reverse('clients:test_center')}?run_id={test_run.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bi-door-open")
        self.assertContains(response, reverse("clients:onboarding_start", kwargs={"token": token}))

        portal_response = self.browser.get(reverse("clients:onboarding_start", kwargs={"token": token}))
        self.assertEqual(portal_response.status_code, 200)
