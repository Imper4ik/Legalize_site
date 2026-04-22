from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from clients.constants import DocumentType
from clients.forms import ClientForm
from clients.models import Client, Document, DocumentRequirement


class WorkflowPolicyStage15Tests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            email="staff-stage15@example.com",
            password="pass",
            is_staff=True,
        )
        self.client_obj = Client.objects.create(
            first_name="Marta",
            last_name="Bilan",
            citizenship="UA",
            phone="+48444444444",
            email="marta-stage15@example.com",
            application_purpose="work",
            workflow_stage="new_client",
            assigned_staff=self.staff,
        )

    def _build_form_data(self, **overrides):
        data = {
            "first_name": self.client_obj.first_name,
            "last_name": self.client_obj.last_name,
            "email": self.client_obj.email,
            "phone": self.client_obj.phone,
            "citizenship": self.client_obj.citizenship,
            "birth_date": "",
            "passport_num": "",
            "case_number": "",
            "application_purpose": self.client_obj.application_purpose,
            "language": self.client_obj.language,
            "company": "",
            "assigned_staff": str(self.staff.pk),
            "status": self.client_obj.status,
            "workflow_stage": self.client_obj.workflow_stage,
            "basis_of_stay": "",
            "legal_basis_end_date": "",
            "submission_date": "",
            "employer_phone": "",
            "fingerprints_date": "",
            "notes": "",
        }
        data.update(overrides)
        return data

    def test_client_form_rejects_skipping_workflow_stages(self):
        form = ClientForm(
            data=self._build_form_data(workflow_stage="decision_received"),
            instance=self.client_obj,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("workflow_stage", form.errors)

    def test_client_form_requires_submission_date_for_fingerprints_stage(self):
        self.client_obj.workflow_stage = "application_submitted"
        form = ClientForm(
            data=self._build_form_data(workflow_stage="fingerprints"),
            instance=self.client_obj,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("workflow_stage", form.errors)

    def test_client_form_requires_all_required_documents_before_submission_stage(self):
        self.client_obj.workflow_stage = "document_collection"
        DocumentRequirement.objects.create(
            application_purpose="work",
            document_type=DocumentType.PASSPORT.value,
            custom_name="Passport",
            is_required=True,
            position=0,
        )
        form = ClientForm(
            data=self._build_form_data(workflow_stage="application_submitted"),
            instance=self.client_obj,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("workflow_stage", form.errors)

    def test_client_form_allows_next_valid_workflow_step_with_required_data(self):
        self.client_obj.workflow_stage = "application_submitted"
        self.client_obj.submission_date = timezone.localdate() - timedelta(days=1)
        form = ClientForm(
            data=self._build_form_data(
                workflow_stage="fingerprints",
                submission_date=self.client_obj.submission_date.isoformat(),
            ),
            instance=self.client_obj,
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_client_form_allows_submission_stage_when_required_documents_complete(self):
        self.client_obj.workflow_stage = "document_collection"
        DocumentRequirement.objects.create(
            application_purpose="work",
            document_type=DocumentType.PASSPORT.value,
            custom_name="Passport",
            is_required=True,
            position=0,
        )
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file=SimpleUploadedFile("passport.pdf", b"pdf-data", content_type="application/pdf"),
        )
        form = ClientForm(
            data=self._build_form_data(workflow_stage="application_submitted"),
            instance=self.client_obj,
        )

        self.assertTrue(form.is_valid(), form.errors)
