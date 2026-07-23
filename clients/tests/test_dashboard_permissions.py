from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from clients.services.roles import ensure_predefined_roles


class DashboardPermissionTests(TestCase):
    def setUp(self):
        ensure_predefined_roles()
        user_model = get_user_model()

        self.staff = user_model.objects.create_user(email="dash-staff@example.com", password="pass", is_staff=True)
        self.staff.groups.add(Group.objects.get(name="Staff"))

        self.manager = user_model.objects.create_user(email="dash-manager@example.com", password="pass", is_staff=True)
        self.manager.groups.add(Group.objects.get(name="Manager"))

        self.admin = user_model.objects.create_user(email="dash-admin@example.com", password="pass", is_staff=True)
        self.admin.groups.add(Group.objects.get(name="Admin"))

    def test_staff_can_access_admin_dashboard(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("clients:admin_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_manager_can_access_admin_dashboard(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("clients:admin_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_admin_can_access_admin_dashboard(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("clients:admin_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_admin_dashboard_context_is_populated(self):
        # Regression: the template used to render empty because the view
        # supplied none of the variables it expects.
        self.client.force_login(self.admin)
        response = self.client.get(reverse("clients:admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        for key in (
            "generated_at",
            "email_status",
            "ocr_status",
            "storage",
            "runtime_dependencies",
            "pending_document_jobs",
            "processing_document_jobs",
            "failed_document_jobs",
            "pending_campaigns",
            "running_campaigns",
            "failed_campaigns",
            "docs_awaiting_confirmation",
            "docs_awaiting_verification",
            "overdue_tasks",
            "docs_name_mismatch",
            "expired_documents",
            "active_reminders",
            "recent_campaigns",
        ):
            self.assertIn(key, response.context, key)
        self.assertIn("css", response.context["email_status"])
        self.assertIn("label", response.context["ocr_status"])
        self.assertIn("total_display", response.context["storage"])

    def test_staff_can_access_metrics_by_default(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("clients:metrics_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_manager_can_access_metrics(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("clients:metrics_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_admin_can_access_metrics(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("clients:metrics_dashboard"))
        self.assertEqual(response.status_code, 200)
