from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clients.models import Client, MOSApplicationData
from clients.services.roles import ensure_predefined_roles


class AdminMOSReviewActionTests(TestCase):
    """POST actions of the MOS review drive case workflow + MOS status together."""

    def setUp(self) -> None:
        ensure_predefined_roles()
        user_model = get_user_model()
        self.manager = user_model.objects.create_user(
            email="mos-actions-manager@example.com",
            password="securepassword",
            is_staff=True,
        )
        self.manager.groups.add(Group.objects.get(name="Manager"))
        self.client_record = Client.objects.create(
            first_name="Anna",
            last_name="Iwanova",
            email="mos-actions-client@example.com",
            application_purpose="work",
        )
        # The post_save signal creates the primary case (with the principal
        # participant) and its MOS record.
        self.case = self.client_record.cases.order_by("id").first()
        self.mos, _ = MOSApplicationData.objects.get_or_create(
            client=self.client_record, case=self.case
        )
        self.mos.status = "client_completed"
        self.mos.save(update_fields=["status"])
        self.review_url = reverse(
            "clients:admin_mos_review", kwargs={"client_id": self.client_record.pk}
        )
        self.client.force_login(self.manager)

    def _post(self, action: str, **extra: str):
        return self.client.post(self.review_url, {"action": action, **extra})

    def test_approve_applies_questionnaire_data_to_client_card(self) -> None:
        self.mos.personal_data = {
            "first_name": "Hanna",
            "last_name": "Ivanova",
            "phone": "+48555666777",
            "birth_date": "1995-04-12",
        }
        self.mos.save(update_fields=["personal_data"])

        response = self._post("approve")

        self.assertEqual(response.status_code, 302)
        self.mos.refresh_from_db()
        self.client_record.refresh_from_db()
        self.assertEqual(self.mos.status, "mos_package_ready")
        self.assertEqual(self.mos.staff_reviewed_by_id, self.manager.pk)
        self.assertIsNotNone(self.mos.staff_reviewed_at)
        self.assertEqual(self.client_record.first_name, "Hanna")
        self.assertEqual(self.client_record.phone, "+48555666777")
        self.assertEqual(str(self.client_record.birth_date), "1995-04-12")

    def test_accept_client_purpose_applies_purpose_to_case(self) -> None:
        self.mos.mos_purpose = "study"
        self.mos.save(update_fields=["mos_purpose"])

        response = self._post("accept_client_purpose")

        self.assertEqual(response.status_code, 302)
        self.case.refresh_from_db()
        self.assertEqual(self.case.application_purpose, "study")

    def test_accept_client_purpose_rejects_unknown_purpose(self) -> None:
        self.mos.mos_purpose = "unsupported_value"
        self.mos.save(update_fields=["mos_purpose"])

        response = self._post("accept_client_purpose")

        self.assertEqual(response.status_code, 302)
        self.case.refresh_from_db()
        self.assertEqual(self.case.application_purpose, "work")

    def test_mark_submitted_blocked_until_required_documents_collected(self) -> None:
        self.case.workflow_stage = "document_collection"
        self.case.save(update_fields=["workflow_stage"])

        response = self._post("mark_submitted")

        self.assertEqual(response.status_code, 302)
        self.case.refresh_from_db()
        self.mos.refresh_from_db()
        self.assertEqual(self.case.workflow_stage, "document_collection")
        self.assertNotEqual(self.mos.status, "submitted_in_mos")

    def test_mark_fingerprints_moves_case_to_fingerprints_stage(self) -> None:
        self.case.workflow_stage = "application_submitted"
        self.case.submission_date = timezone.localdate()
        self.case.save(update_fields=["workflow_stage", "submission_date"])

        response = self._post("mark_fingerprints")

        self.assertEqual(response.status_code, 302)
        self.case.refresh_from_db()
        self.mos.refresh_from_db()
        self.assertEqual(self.case.workflow_stage, "fingerprints")
        self.assertEqual(self.mos.status, "fingerprints")

    def test_mark_fingerprints_with_past_date_jumps_to_waiting_decision(self) -> None:
        self.case.workflow_stage = "application_submitted"
        self.case.submission_date = timezone.localdate() - timedelta(days=10)
        self.case.fingerprints_date = timezone.localdate() - timedelta(days=1)
        self.case.save(update_fields=["workflow_stage", "submission_date", "fingerprints_date"])

        response = self._post("mark_fingerprints")

        self.assertEqual(response.status_code, 302)
        self.case.refresh_from_db()
        self.assertEqual(self.case.workflow_stage, "waiting_decision")

    def test_mark_waiting_requires_fingerprints_date(self) -> None:
        self.case.workflow_stage = "fingerprints"
        self.case.fingerprints_date = None
        self.case.save(update_fields=["workflow_stage", "fingerprints_date"])

        response = self._post("mark_waiting")

        self.assertEqual(response.status_code, 302)
        self.case.refresh_from_db()
        self.mos.refresh_from_db()
        self.assertEqual(self.case.workflow_stage, "fingerprints")
        self.assertNotEqual(self.mos.status, "waiting_decision")

    def test_mark_waiting_moves_case_when_fingerprints_date_present(self) -> None:
        self.case.workflow_stage = "fingerprints"
        self.case.submission_date = timezone.localdate() - timedelta(days=10)
        self.case.fingerprints_date = timezone.localdate() - timedelta(days=1)
        self.case.save(update_fields=["workflow_stage", "submission_date", "fingerprints_date"])

        response = self._post("mark_waiting")

        self.assertEqual(response.status_code, 302)
        self.case.refresh_from_db()
        self.mos.refresh_from_db()
        self.assertEqual(self.case.workflow_stage, "waiting_decision")
        self.assertEqual(self.mos.status, "waiting_decision")

    def test_mark_decision_requires_decision_date(self) -> None:
        self.case.workflow_stage = "waiting_decision"
        self.case.decision_date = None
        self.case.save(update_fields=["workflow_stage", "decision_date"])

        response = self._post("mark_decision")

        self.assertEqual(response.status_code, 302)
        self.case.refresh_from_db()
        self.assertEqual(self.case.workflow_stage, "waiting_decision")

    def test_mark_decision_moves_case_when_decision_date_present(self) -> None:
        self.case.workflow_stage = "waiting_decision"
        self.case.submission_date = timezone.localdate() - timedelta(days=30)
        self.case.fingerprints_date = timezone.localdate() - timedelta(days=20)
        self.case.decision_date = timezone.localdate()
        self.case.save(
            update_fields=["workflow_stage", "submission_date", "fingerprints_date", "decision_date"]
        )

        response = self._post("mark_decision")

        self.assertEqual(response.status_code, 302)
        self.case.refresh_from_db()
        self.mos.refresh_from_db()
        self.assertEqual(self.case.workflow_stage, "decision_received")
        self.assertEqual(self.mos.status, "decision_received")
