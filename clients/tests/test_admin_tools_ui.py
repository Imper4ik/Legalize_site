from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client as DjangoClient
from django.test import TestCase
from django.urls import reverse


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

    def test_test_center_uses_test_workbench_layout(self) -> None:
        response = self.browser.get(reverse("clients:test_center"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "test-workbench")
        self.assertContains(response, "tc-mode-list")
        self.assertContains(response, "tc-mode-card")
        self.assertContains(response, "Smoke")
