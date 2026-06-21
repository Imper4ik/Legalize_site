from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from clients.constants import DocumentType
from clients.models import Client, Document, MOSApplicationData, Payment, StaffTask
from clients.services.roles import ensure_predefined_roles
from clients.services.workday import build_workday_context


@override_settings(LANGUAGE_CODE="ru")
class WorkdayViewTests(TestCase):
    def setUp(self):
        ensure_predefined_roles()
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(email="admin-workday@example.com", password="pass", is_staff=True)
        self.admin.groups.add(Group.objects.get(name="Admin"))
        self.staff = user_model.objects.create_user(email="staff-workday@example.com", password="pass", is_staff=True)
        self.staff.groups.add(Group.objects.get(name="Staff"))
        self.other_staff = user_model.objects.create_user(email="other-staff-workday@example.com", password="pass", is_staff=True)
        self.other_staff.groups.add(Group.objects.get(name="Staff"))

    def _file(self, name: str = "doc.pdf") -> SimpleUploadedFile:
        return SimpleUploadedFile(name, b"file", content_type="application/pdf")

    def test_workday_service_collects_operational_sections(self):
        today = date(2026, 6, 20)
        review_client = Client.objects.create(first_name="Review", last_name="Client")
        Document.objects.create(
            client=review_client,
            document_type=DocumentType.PASSPORT.value,
            file=self._file("review.pdf"),
            verified=False,
        )

        new_card_client = Client.objects.create(first_name="NewCard", last_name="MissingCase")
        mos_data = new_card_client.mos_application_data
        mos_data.new_residence_card_application_status = MOSApplicationData.NEW_CARD_STATUS_YES
        mos_data.new_residence_card_submitted_at = today - timedelta(days=3)
        mos_data.save(update_fields=["new_residence_card_application_status", "new_residence_card_submitted_at"])

        fingerprints_client = Client.objects.create(
            first_name="Fingerprints",
            last_name="Followup",
            workflow_stage="waiting_decision",
            fingerprints_date=today - timedelta(days=120),
        )
        Payment.objects.create(
            client=fingerprints_client,
            service_description="consultation",
            total_amount="300.00",
            amount_paid="0.00",
            status="pending",
            due_date=today - timedelta(days=1),
        )
        StaffTask.objects.create(
            client=fingerprints_client,
            title="Check status",
            due_date=today - timedelta(days=2),
            status="open",
        )

        context = build_workday_context(self.admin, today=today, limit_per_section=10)
        sections = {section["key"]: section for section in context["workday_sections"]}

        self.assertEqual(sections["documents_review"]["count"], 1)
        self.assertEqual(sections["new_card_missing_case"]["count"], 1)
        self.assertEqual(sections["fingerprints_followup"]["count"], 1)
        self.assertEqual(sections["overdue_tasks"]["count"], 1)
        self.assertEqual(sections["overdue_payments"]["count"], 1)
        self.assertGreaterEqual(sections["zus_rca"]["count"], 1)
        self.assertTrue(context["has_workday_items"])

    def test_workday_service_gives_global_visibility_to_staff(self):
        today = date(2026, 6, 20)
        visible_client = Client.objects.create(first_name="Visible", last_name="Client", assigned_staff=self.staff)
        hidden_client = Client.objects.create(first_name="Hidden", last_name="Client", assigned_staff=self.other_staff)
        Document.objects.create(
            client=visible_client,
            document_type=DocumentType.PASSPORT.value,
            file=self._file("visible.pdf"),
            verified=False,
        )
        Document.objects.create(
            client=hidden_client,
            document_type=DocumentType.PASSPORT.value,
            file=self._file("hidden.pdf"),
            verified=False,
        )

        context = build_workday_context(self.staff, today=today, limit_per_section=10)
        review_items = context["workday_sections"][0]["items"]
        names = {str(item["client"]) for item in review_items}

        self.assertIn("Visible Client", names)
        self.assertIn("Hidden Client", names)

    def test_workday_page_renders_for_staff(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("clients:workday"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Рабочий день")
        self.assertContains(response, "Документы на проверку")
        self.assertContains(response, "Новая подача без номера дела")

    def test_workday_prioritizes_items_correctly(self):
        today = date(2026, 6, 20)

        # Client whose stay is expiring soon (<= 30 days)
        critical_client = Client.objects.create(
            first_name="Critical",
            last_name="Stay",
            legal_basis_end_date=today + timedelta(days=15),
        )
        Document.objects.create(
            client=critical_client,
            document_type=DocumentType.PASSPORT.value,
            file=self._file("passport.pdf"),
            verified=False,
        )

        # Normal client with missing documents (should be important)
        normal_client = Client.objects.create(
            first_name="Normal",
            last_name="Client",
            legal_basis_end_date=today + timedelta(days=100),
        )
        Document.objects.create(
            client=normal_client,
            document_type=DocumentType.PASSPORT.value,
            file=self._file("normal_passport.pdf"),
            verified=False,
        )

        context = build_workday_context(self.admin, today=today, limit_per_section=10)
        review_items = {item["client"].last_name: item for item in context["workday_sections"][0]["items"]}

        self.assertEqual(review_items["Stay"]["priority"], "urgent")
        self.assertEqual(review_items["Client"]["priority"], "important")
        self.assertEqual(context["urgent_count"], 2)
        self.assertEqual(context["important_count"], 2)
