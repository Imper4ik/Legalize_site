from __future__ import annotations

from io import StringIO
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, Client as DjangoClient, override_settings
from django.urls import reverse

from clients.models import (
    Client,
    Document,
    Payment,
    EmailLog,
    ClientOnboardingSession,
    ClientActivity,
    DocumentProcessingJob,
)
from clients.demo.demo_factory import get_demo_token_for_client


class DemoCenterTests(TestCase):
    def setUp(self) -> None:
        self.user_model = get_user_model()
        self.superuser = self.user_model.objects.create_superuser(
            email="super@example.demo",
            password="pass",
        )
        self.staff_user = self.user_model.objects.create_user(
            email="staff@example.demo",
            password="pass",
            is_staff=True,
        )
        self.client_user = self.user_model.objects.create_user(
            email="client@example.demo",
            password="pass",
        )
        self.browser = DjangoClient()

    def test_ordinary_staff_cannot_open_demo_center(self) -> None:
        self.browser.force_login(self.staff_user)
        response = self.browser.get(reverse("clients:demo_center"))
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_open_demo_center(self) -> None:
        self.browser.force_login(self.superuser)
        response = self.browser.get(reverse("clients:demo_center"))
        self.assertEqual(response.status_code, 200)

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        },
    )
    def test_prepare_demo_scenarios(self) -> None:
        self.browser.force_login(self.superuser)
        
        # Prepare demo via POST
        response = self.browser.post(reverse("clients:demo_center"), {"action": "prepare"})
        self.assertEqual(response.status_code, 302)

        # Assert 5 clients are created with is_demo_data=True
        demo_clients = Client.all_objects.filter(is_demo_data=True)
        self.assertEqual(demo_clients.count(), 5)
        
        # Check specific names
        first_names = set(demo_clients.values_list("first_name", flat=True))
        expected_names = {"Jan", "Anna", "Daria", "Ivan", "Maria"}
        self.assertEqual(first_names, expected_names)

        # Assert related models are populated
        self.assertTrue(Document.all_objects.filter(is_demo_data=True).exists())
        self.assertTrue(Payment.all_objects.filter(is_demo_data=True).exists())
        self.assertTrue(EmailLog.objects.filter(is_demo_data=True).exists())
        self.assertTrue(ClientOnboardingSession.objects.filter(is_demo_data=True).exists())
        self.assertTrue(ClientActivity.objects.filter(is_demo_data=True).exists())
        self.assertTrue(DocumentProcessingJob.objects.filter(is_demo_data=True).exists())

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        },
    )
    def test_reset_demo_data(self) -> None:
        self.browser.force_login(self.superuser)
        
        # Prepare first
        self.browser.post(reverse("clients:demo_center"), {"action": "prepare"})
        self.assertEqual(Client.all_objects.filter(is_demo_data=True).count(), 5)

        # Add a non-demo client to make sure it is not deleted
        non_demo_client = Client.objects.create(
            first_name="Real",
            last_name="User",
            email="real@example.com",
            is_demo_data=False,
        )

        # Clean demo data via POST
        response = self.browser.post(reverse("clients:demo_center"), {"action": "clean", "confirm_clean": "yes"})
        self.assertEqual(response.status_code, 302)

        # Assert demo clients are deleted but real client remains
        self.assertEqual(Client.all_objects.filter(is_demo_data=True).count(), 0)
        self.assertEqual(Client.objects.filter(is_demo_data=False).count(), 1)
        self.assertEqual(Client.objects.get(pk=non_demo_client.pk).first_name, "Real")

    def test_onboarding_session_portal_links(self) -> None:
        client = Client.objects.create(
            first_name="Test",
            last_name="User",
            email="test@example.demo",
            is_demo_data=True,
        )
        token = get_demo_token_for_client(client)
        self.assertIn("demo-token-", token)

    def test_clean_demo_command_requires_confirm(self) -> None:
        with self.assertRaises(CommandError):
            call_command("clean_demo_data", stdout=StringIO())
