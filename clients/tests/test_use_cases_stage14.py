from __future__ import annotations

from datetime import timedelta
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from clients.models import Client, ClientActivity, DocumentRequirement
from clients.use_cases.client_records import (
    finalize_client_creation,
    finalize_client_update,
    snapshot_client_update_state,
)
from clients.use_cases.document_requirements import (
    build_document_requirement_code,
    create_document_requirement_for_purpose,
    delete_document_requirement_record,
    sync_document_checklist_for_purpose,
    update_document_requirement_record,
)


class UseCasesStage14Tests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            email="staff-stage14@example.com",
            password="pass",
            is_staff=True,
        )
        self.client_obj = Client.objects.create(
            first_name="Daria",
            last_name="Kravets",
            citizenship="UA",
            phone="+48333333333",
            email="daria-stage14@example.com",
            application_purpose="work",
            workflow_stage="new_client",
        )

    def test_finalize_client_creation_logs_activity_and_calls_notification(self):
        send_required_email = Mock(return_value=1)

        result = finalize_client_creation(
            client=self.client_obj,
            actor=self.staff,
            send_required_email=send_required_email,
        )

        self.assertTrue(result.required_documents_email_sent)
        send_required_email.assert_called_once_with(self.client_obj)
        activity = ClientActivity.objects.get(client=self.client_obj, event_type="client_created")
        self.assertEqual(activity.actor, self.staff)
        self.assertEqual(activity.metadata["workflow_stage"], "new_client")

    def test_finalize_client_update_logs_changed_fields_and_workflow_change(self):
        previous_values = snapshot_client_update_state(self.client_obj)
        previous_fingerprints_date = self.client_obj.fingerprints_date
        new_fingerprints_date = timezone.localdate() + timedelta(days=9)
        self.client_obj.workflow_stage = "document_collection"
        self.client_obj.notes = "Waiting for updated documents."
        self.client_obj.fingerprints_date = new_fingerprints_date
        self.client_obj.save(update_fields=["workflow_stage", "notes", "fingerprints_date"])
        send_expired_email = Mock(return_value=1)

        result = finalize_client_update(
            client=self.client_obj,
            actor=self.staff,
            previous_values=previous_values,
            previous_fingerprints_date=previous_fingerprints_date,
            new_fingerprints_date=new_fingerprints_date,
            send_expired_email=send_expired_email,
        )

        self.assertEqual(result.changed_fields, ("workflow_stage", "fingerprints_date", "notes"))
        self.assertTrue(result.workflow_changed)
        self.assertTrue(result.expired_documents_email_sent)
        send_expired_email.assert_called_once_with(self.client_obj)
        self.assertTrue(
            ClientActivity.objects.filter(client=self.client_obj, event_type="client_updated").exists()
        )
        workflow_activity = ClientActivity.objects.get(client=self.client_obj, event_type="workflow_changed")
        self.assertEqual(workflow_activity.metadata["workflow_stage"], "document_collection")

    def test_finalize_client_update_skips_logging_when_nothing_changed(self):
        previous_values = snapshot_client_update_state(self.client_obj)
        send_expired_email = Mock(return_value=1)

        result = finalize_client_update(
            client=self.client_obj,
            actor=self.staff,
            previous_values=previous_values,
            previous_fingerprints_date=self.client_obj.fingerprints_date,
            new_fingerprints_date=self.client_obj.fingerprints_date,
            send_expired_email=send_expired_email,
        )

        self.assertEqual(result.changed_fields, ())
        self.assertFalse(result.workflow_changed)
        self.assertFalse(result.expired_documents_email_sent)
        send_expired_email.assert_not_called()
        self.assertFalse(
            ClientActivity.objects.filter(client=self.client_obj, event_type="client_updated").exists()
        )

    def test_build_document_requirement_code_returns_unique_slug(self):
        DocumentRequirement.objects.create(
            application_purpose="work",
            document_type="bank_statement",
            custom_name="Bank Statement",
            is_required=True,
            position=0,
        )

        code = build_document_requirement_code(purpose="work", name="Bank Statement")

        self.assertNotEqual(code, "bank_statement")
        self.assertTrue(code.startswith("bank_statement"))

    def test_create_document_requirement_for_purpose_creates_positioned_record(self):
        DocumentRequirement.objects.create(
            application_purpose="work",
            document_type="passport",
            custom_name="Passport",
            is_required=True,
            position=0,
        )

        result = create_document_requirement_for_purpose(
            purpose="work",
            name="Proof of address",
            slug="proof_of_address",
        )

        self.assertEqual(result.requirement.document_type, "proof_of_address")
        self.assertEqual(result.requirement.position, 1)
        self.assertTrue(result.requirement.is_required)

    def test_update_document_requirement_record_propagates_default_name_to_empty_locales(self):
        requirement = DocumentRequirement.objects.create(
            application_purpose="work",
            document_type="proof_of_income",
            custom_name="Income proof",
            custom_name_pl="",
            custom_name_en="",
            custom_name_ru="",
            is_required=True,
            position=0,
        )

        result = update_document_requirement_record(
            requirement=requirement,
            cleaned_data={
                "custom_name": "Updated income proof",
                "custom_name_pl": "",
                "custom_name_en": "",
                "custom_name_ru": "",
                "is_required": False,
            },
        )

        requirement.refresh_from_db()
        self.assertEqual(result.requirement_name, "Updated income proof")
        self.assertEqual(requirement.custom_name_pl, "Updated income proof")
        self.assertEqual(requirement.custom_name_en, "Updated income proof")
        self.assertEqual(requirement.custom_name_ru, "Updated income proof")
        self.assertFalse(requirement.is_required)

    def test_delete_document_requirement_record_removes_requirement(self):
        requirement = DocumentRequirement.objects.create(
            application_purpose="work",
            document_type="employment_contract",
            custom_name="Employment contract",
            is_required=True,
            position=0,
        )

        result = delete_document_requirement_record(requirement=requirement)

        self.assertEqual(result.deleted_requirement_id, requirement.pk)
        self.assertEqual(result.requirement_name, "Employment contract")
        self.assertFalse(DocumentRequirement.objects.filter(pk=requirement.pk).exists())

    def test_sync_document_checklist_for_purpose_updates_existing_and_new_records(self):
        retained = DocumentRequirement.objects.create(
            application_purpose="work",
            document_type="passport",
            custom_name="Passport",
            is_required=True,
            position=3,
        )
        removed = DocumentRequirement.objects.create(
            application_purpose="work",
            document_type="old_code",
            custom_name="Old code",
            is_required=True,
            position=1,
        )

        result = sync_document_checklist_for_purpose(
            purpose="work",
            selected_codes=["passport", "proof_of_address"],
        )

        retained.refresh_from_db()
        removed.refresh_from_db()
        created = DocumentRequirement.objects.get(application_purpose="work", document_type="proof_of_address")

        self.assertEqual(result.updated_count, 2)
        self.assertEqual(result.selected_codes, ("passport", "proof_of_address"))
        self.assertEqual(retained.position, 0)
        self.assertTrue(retained.is_required)
        self.assertEqual(created.position, 1)
        self.assertTrue(created.is_required)
        self.assertFalse(removed.is_required)
