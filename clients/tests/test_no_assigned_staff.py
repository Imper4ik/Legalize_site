"""Spec §2: there is no per-client / per-case "responsible staff".

Every internal staff member has office-wide access to all clients and cases.
The ``assigned_staff`` field has been dropped from the Client and Case domain,
their forms, templates, notifications and queues. ``StaffTask.assignee`` is the
only surviving notion of a task executor and it never restricts who may view or
edit a case.
"""
from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from clients.forms import CaseForm, ClientForm
from clients.models import Case, StaffTask
from clients.services.cases import create_case_for_client
from clients.services.notifications import _staff_notification_recipients_for_client
from clients.testing.factories import (
    TEST_USER_CREDENTIAL,
    create_test_client,
    create_test_user,
)


class AssignedStaffRemovedTests(TestCase):
    def setUp(self) -> None:
        self.staff_a = create_test_user(role="Staff", email="staff-a-noassign@example.com")
        self.staff_b = create_test_user(role="Staff", email="staff-b-noassign@example.com")

    # --- field is gone from the models -------------------------------------
    def test_models_have_no_assigned_staff_field(self) -> None:
        client_fields = {f.name for f in create_test_client()._meta.get_fields()}
        case_fields = {f.name for f in Case._meta.get_fields()}
        self.assertNotIn("assigned_staff", client_fields)
        self.assertNotIn("assigned_staff", case_fields)

    # --- forms expose no responsible-staff control -------------------------
    def test_client_and_case_forms_have_no_assigned_field(self) -> None:
        self.assertNotIn("assigned_staff", CaseForm().fields)
        client_form = ClientForm(user=self.staff_a)
        self.assertNotIn("assigned_staff", client_form.fields)
        # No field is labelled as a responsible/assigned officer either.
        labels = " ".join(str(f.label or "") for f in client_form.fields.values())
        for banned in ("Ответственный сотрудник", "Назначенный", "Закреплённый"):
            self.assertNotIn(banned, labels)

    # --- any staff can open and edit any case ------------------------------
    def test_staff_a_can_edit_case_created_in_context_of_staff_b(self) -> None:
        client = create_test_client(first_name="Cross", last_name="Access")
        case = create_case_for_client(client=client, actor=self.staff_b)

        self.client.login(email=self.staff_a.email, password=TEST_USER_CREDENTIAL)

        detail = self.client.get(reverse("clients:case_detail", kwargs={"pk": case.pk}))
        self.assertEqual(detail.status_code, 200)

        edit = self.client.post(
            reverse("clients:case_edit", kwargs={"pk": case.pk}),
            data={
                "authority_case_number": "WSC-II-P.6151.111.2026",
                "application_purpose": case.application_purpose,
                "application_type": "",
                "basis_of_stay": "",
                "workflow_stage": case.workflow_stage,
                "submission_date": "",
                "fingerprints_date": "",
                "company": "",
                "version": case.version,
            },
        )
        self.assertEqual(edit.status_code, 302)
        case.refresh_from_db()
        self.assertEqual(case.authority_case_number, "WSC-II-P.6151.111.2026")

    # --- notifications never resolve a recipient via assigned staff --------
    def test_staff_notifications_use_office_mailbox_not_assigned_staff(self) -> None:
        client = create_test_client(first_name="Notify", last_name="Office")
        with patch(
            "clients.services.notifications._get_staff_recipients",
            return_value=["office@example.com"],
        ):
            recipients = _staff_notification_recipients_for_client(client)
        self.assertEqual(recipients, ["office@example.com"])

    # --- task assignee does not gate case access ---------------------------
    def test_task_assignee_does_not_restrict_case_access_for_other_staff(self) -> None:
        client = create_test_client(first_name="Task", last_name="Scope")
        case = create_case_for_client(client=client, actor=self.staff_b)
        # The task is assigned to staff_b specifically.
        StaffTask.objects.create(
            client=client,
            case=case,
            title="Follow up",
            assignee=self.staff_b,
        )

        # staff_a (not the assignee) still has full access to the case.
        self.client.login(email=self.staff_a.email, password=TEST_USER_CREDENTIAL)
        detail = self.client.get(reverse("clients:case_detail", kwargs={"pk": case.pk}))
        self.assertEqual(detail.status_code, 200)
