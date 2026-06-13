from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse

from clients.models import Client, ClientDocumentRequirement, Reminder
from clients.services.roles import ensure_predefined_roles


@override_settings(LANGUAGE_CODE="ru")
class DocumentReminderMissingViewTests(TestCase):
    def setUp(self) -> None:
        ensure_predefined_roles()
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            email="missing-view-staff@example.test",
            password="pass",
            is_staff=True,
        )
        self.staff.groups.add(Group.objects.get(name="Admin"))
        self.client.force_login(self.staff)

    def test_missing_mode_lists_checklist_items_without_reminders(self) -> None:
        client_record = Client.objects.create(
            first_name="Missing",
            last_name="Docs",
            email="missing-docs@example.test",
            application_purpose="work",
        )
        ClientDocumentRequirement.objects.create(
            client=client_record,
            name="Special missing permit confirmation",
            is_required=True,
        )

        response = self.client.get(f"{reverse('clients:document_reminder_list')}?view=missing")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Reminder.objects.filter(client=client_record).count(), 0)
        self.assertTrue(response.context["missing_only"])
        self.assertEqual(response.context["missing_clients_count"], 1)
        self.assertGreaterEqual(response.context["total_missing_documents_count"], 1)
        self.assertContains(response, "Missing Docs")
        self.assertContains(response, "Special missing permit confirmation")

    def test_admin_panel_missing_documents_card_opens_missing_mode(self) -> None:
        response = self.client.get(reverse("clients:admin_panel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'{reverse("clients:document_reminder_list")}?view=missing#documents-section',
        )
