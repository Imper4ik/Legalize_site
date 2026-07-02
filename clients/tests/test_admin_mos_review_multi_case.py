from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from clients.models import Client, MOSApplicationData
from clients.services.cases import create_case_for_client
from clients.services.roles import ensure_predefined_roles


class AdminMOSReviewMultiCaseTests(TestCase):
    """A client with several case-scoped questionnaires must never 500 the review."""

    def setUp(self) -> None:
        ensure_predefined_roles()
        user_model = get_user_model()
        self.manager = user_model.objects.create_user(
            email="mos-review-manager@example.com",
            password="securepassword",
            is_staff=True,
        )
        self.manager.groups.add(Group.objects.get(name="Manager"))
        self.client_record = Client.objects.create(
            first_name="Multi",
            last_name="Case",
            email="multi-case-review@example.com",
            application_purpose="work",
        )
        # The post_save signal creates the primary case; add a second one.
        self.first_case = self.client_record.cases.order_by("id").first()
        self.second_case = create_case_for_client(
            client=self.client_record,
            application_purpose="study",
            workflow_stage="new_client",
        )
        # The post_save signal already creates the MOS record for the primary case.
        self.first_mos, _ = MOSApplicationData.objects.get_or_create(
            client=self.client_record, case=self.first_case
        )
        self.first_mos.status = "client_completed"
        self.first_mos.save(update_fields=["status"])
        self.second_mos, _ = MOSApplicationData.objects.get_or_create(
            client=self.client_record, case=self.second_case
        )
        self.second_mos.status = "client_filling"
        self.second_mos.save(update_fields=["status"])
        self.review_url = reverse(
            "clients:admin_mos_review", kwargs={"client_id": self.client_record.pk}
        )
        self.client.force_login(self.manager)

    def test_without_case_param_shows_case_picker(self) -> None:
        response = self.client.get(self.review_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "clients/mos_review_select_case.html")
        self.assertContains(response, f"case={self.first_case.uuid}")
        self.assertContains(response, f"case={self.second_case.uuid}")

    def test_with_case_param_opens_scoped_review(self) -> None:
        response = self.client.get(f"{self.review_url}?case={self.second_case.uuid}")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "clients/mos_review.html")
        self.assertEqual(response.context["mos_data"].pk, self.second_mos.pk)

    def test_unknown_case_param_returns_404(self) -> None:
        response = self.client.get(
            f"{self.review_url}?case=00000000-0000-0000-0000-000000000000"
        )
        self.assertEqual(response.status_code, 404)

    def test_post_action_acts_on_selected_case_only(self) -> None:
        response = self.client.post(
            f"{self.review_url}?case={self.first_case.uuid}",
            {"action": "request_correction", "correction_message": "fix it"},
        )

        self.assertEqual(response.status_code, 302)
        self.first_mos.refresh_from_db()
        self.second_mos.refresh_from_db()
        self.assertEqual(self.first_mos.status, "needs_correction")
        self.assertEqual(self.second_mos.status, "client_filling")

    def test_single_record_client_resolves_without_case_param(self) -> None:
        single_client = Client.objects.create(
            first_name="Single",
            last_name="Case",
            email="single-case-review@example.com",
            application_purpose="work",
        )
        case = single_client.cases.first()
        mos, _ = MOSApplicationData.objects.get_or_create(client=single_client, case=case)
        mos.status = "client_completed"
        mos.save(update_fields=["status"])

        response = self.client.get(
            reverse("clients:admin_mos_review", kwargs={"client_id": single_client.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "clients/mos_review.html")
