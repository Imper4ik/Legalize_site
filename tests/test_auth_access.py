"""Tests for authentication and access control.

Verifies that staff-only views redirect unauthenticated users to login,
and return 403 for non-staff authenticated users.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, Client as DjangoClient
from django.urls import reverse

User = get_user_model()


class AuthAccessBaseTest(TestCase):
    """Base class with common user fixtures."""

    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create_user(
            username="staff", email="staff@test.com", password="testpass123", is_staff=True
        )
        cls.regular_user = User.objects.create_user(
            username="regular", email="regular@test.com", password="testpass123", is_staff=False
        )

    def setUp(self):
        self.client = DjangoClient()


class StaffViewAccessTest(AuthAccessBaseTest):
    """Staff-guarded CBV views redirect anonymous and forbid non-staff."""

    STAFF_URLS = [
        ("clients:client_list", {}),
        ("clients:mass_email", {}),
        ("clients:metrics_dashboard", {}),
        ("clients:document_reminder_list", {}),
        ("clients:payment_reminder_list", {}),
    ]

    def test_anonymous_redirected_to_login(self):
        for url_name, kwargs in self.STAFF_URLS:
            url = reverse(url_name, kwargs=kwargs)
            resp = self.client.get(url)
            self.assertIn(resp.status_code, (301, 302), msg=f"{url_name} should redirect anonymous")

    def test_non_staff_gets_forbidden(self):
        self.client.login(username="regular", password="testpass123")
        for url_name, kwargs in self.STAFF_URLS:
            url = reverse(url_name, kwargs=kwargs)
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 403, msg=f"{url_name} should forbid non-staff")

    def test_staff_can_access(self):
        self.client.login(username="staff", password="testpass123")
        for url_name, kwargs in self.STAFF_URLS:
            url = reverse(url_name, kwargs=kwargs)
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, msg=f"{url_name} should allow staff")


class DashboardRedirectTest(AuthAccessBaseTest):
    """Dashboard view redirects based on user type."""

    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(reverse("root_dashboard"))
        self.assertEqual(resp.status_code, 302)

    def test_staff_redirects_to_client_list(self):
        self.client.login(username="staff", password="testpass123")
        resp = self.client.get(reverse("root_dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/staff/", resp.url)

    def test_non_staff_gets_403(self):
        self.client.login(username="regular", password="testpass123")
        resp = self.client.get(reverse("root_dashboard"))
        self.assertEqual(resp.status_code, 403)
