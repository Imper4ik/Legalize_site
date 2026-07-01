from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from clients.constants import DocumentType
from clients.models import DocumentProcessingJob, DocumentRequirement, EmailLog, Reminder
from clients.services.case_context import (
    build_case_document_checklist,
    checklist_for_case,
    purpose_context_for_case,
    purpose_for_case,
)
from clients.services.cases import create_case_for_client
from clients.services.notifications import _get_missing_documents_context, send_expiring_documents_email
from clients.services.wniosek import create_wniosek_submission, get_submitted_document_codes
from clients.testing.factories import create_test_client, create_test_document
from clients.use_cases.reminders import send_document_reminder_for_client


class CaseFirstProcessIsolationTests(TestCase):
    def setUp(self) -> None:
        self.client_obj = create_test_client(purpose="work", language="en")
        self.case_a = self.client_obj.cases.get()
        self.case_a.application_purpose = "work"
        self.case_a.save(update_fields=["application_purpose"])
        self.case_b = create_case_for_client(client=self.client_obj, application_purpose="study")

    def test_case_checklist_uses_case_purpose_not_client_purpose(self) -> None:
        DocumentRequirement.objects.create(
            application_purpose="work",
            document_type="work_only_contract",
            custom_name_en="Work-only contract",
            is_required=True,
        )
        DocumentRequirement.objects.create(
            application_purpose="study",
            document_type="study_only_certificate",
            custom_name_en="Study-only certificate",
            is_required=True,
        )

        case_b_codes = {item["code"] for item in checklist_for_case(self.case_b, "en", include_fallback=False)}

        self.assertEqual(purpose_for_case(self.case_b), "study")
        self.assertIn("study_only_certificate", case_b_codes)
        self.assertNotIn("work_only_contract", case_b_codes)

    def test_wniosek_submitted_documents_are_scoped_to_selected_case(self) -> None:
        create_wniosek_submission(
            client=self.client_obj,
            case=self.case_a,
            document_kind="temporary_residence",
            attachment_names=["passport"],
            language="en",
        )

        self.assertIn(DocumentType.PASSPORT.value, get_submitted_document_codes(self.client_obj, case=self.case_a))
        self.assertNotIn(DocumentType.PASSPORT.value, get_submitted_document_codes(self.client_obj, case=self.case_b))

    def test_missing_documents_context_does_not_count_wniosek_from_another_case(self) -> None:
        DocumentRequirement.objects.create(
            application_purpose="study",
            document_type=DocumentType.PASSPORT.value,
            custom_name_en="Passport for study case",
            is_required=True,
        )
        create_wniosek_submission(
            client=self.client_obj,
            case=self.case_a,
            document_kind="temporary_residence",
            attachment_names=["passport"],
            language="en",
        )

        context = _get_missing_documents_context(self.client_obj, "en", case=self.case_b)

        self.assertIsNotNone(context)
        missing_names = {item["name"] for item in context["documents"]}
        self.assertIn("Passport for study case", missing_names)

    def test_document_processing_job_rejects_case_that_differs_from_document_case(self) -> None:
        document = create_test_document(self.client_obj, case=self.case_a)

        with self.assertRaises(ValidationError):
            DocumentProcessingJob.objects.create(
                document=document,
                case=self.case_b,
                job_type=DocumentProcessingJob.JOB_TYPE_PASSPORT_OCR,
            )

    def test_document_processing_job_autofills_document_case(self) -> None:
        document = create_test_document(self.client_obj, case=self.case_a)

        job = DocumentProcessingJob.objects.create(
            document=document,
            job_type=DocumentProcessingJob.JOB_TYPE_PASSPORT_OCR,
        )

        self.assertEqual(job.case_id, self.case_a.pk)

    def test_process_email_logs_are_bound_to_the_supplied_case(self) -> None:
        document = create_test_document(
            self.client_obj,
            case=self.case_b,
            expiry_date=timezone.localdate() + timedelta(days=2),
        )

        sent_count = send_expiring_documents_email(self.client_obj, [document], case=self.case_b)

        self.assertEqual(sent_count, 0)
        log = EmailLog.objects.get(client=self.client_obj, template_type="expiring_documents")
        self.assertEqual(log.case_id, self.case_b.pk)
        self.assertIn(str(self.case_b.pk), log.idempotency_key)

    def test_expiring_documents_email_rejects_documents_from_other_case(self) -> None:
        document = create_test_document(
            self.client_obj,
            case=self.case_a,
            expiry_date=timezone.localdate() + timedelta(days=2),
        )

        with self.assertRaises(ValueError):
            send_expiring_documents_email(self.client_obj, [document], case=self.case_b)

    def test_family_cases_use_case_family_role_not_client_purpose(self) -> None:
        self.client_obj.application_purpose = "work"
        self.client_obj.family_role = ""
        self.client_obj.save(update_fields=["application_purpose", "family_role"])
        spouse_case = create_case_for_client(
            client=self.client_obj,
            application_purpose="family",
            family_role="family_spouse",
        )
        child_case = create_case_for_client(
            client=self.client_obj,
            application_purpose="family",
            family_role="family_child",
        )
        DocumentRequirement.objects.create(
            application_purpose="work",
            document_type="work_requirement",
            custom_name_en="Work requirement",
            is_required=True,
        )
        DocumentRequirement.objects.create(
            application_purpose="family_spouse",
            document_type="spouse_requirement",
            custom_name_en="Spouse requirement",
            is_required=True,
        )
        DocumentRequirement.objects.create(
            application_purpose="family_child",
            document_type="child_requirement",
            custom_name_en="Child requirement",
            is_required=True,
        )

        spouse_codes = {item["code"] for item in build_case_document_checklist(spouse_case)}
        child_codes = {item["code"] for item in build_case_document_checklist(child_case)}

        self.assertEqual(purpose_for_case(spouse_case), "family_spouse")
        self.assertEqual(purpose_for_case(child_case), "family_child")
        self.assertIn("spouse_requirement", spouse_codes)
        self.assertNotIn("work_requirement", spouse_codes)
        self.assertIn("child_requirement", child_codes)
        self.assertNotIn("work_requirement", child_codes)

    def test_purpose_context_exposes_case_key_while_preserving_legacy_alias(self) -> None:
        context = purpose_context_for_case(self.case_b)

        self.assertEqual(context["original_case_purpose"], "study")
        self.assertEqual(context["original_client_purpose"], "study")

    def test_manual_document_reminder_sends_one_email_per_case(self) -> None:
        document_a = create_test_document(
            self.client_obj,
            case=self.case_a,
            expiry_date=timezone.localdate() + timedelta(days=2),
        )
        document_b = create_test_document(
            self.client_obj,
            case=self.case_b,
            expiry_date=timezone.localdate() + timedelta(days=3),
        )
        Reminder.objects.create(
            client=self.client_obj,
            case=self.case_a,
            document=document_a,
            reminder_type="document",
            title="Case A document",
            due_date=timezone.localdate(),
            is_active=True,
        )
        Reminder.objects.create(
            client=self.client_obj,
            case=self.case_b,
            document=document_b,
            reminder_type="document",
            title="Case B document",
            due_date=timezone.localdate(),
            is_active=True,
        )
        calls = []

        def fake_sender(client, documents, *, sent_by=None, case=None):
            calls.append((case.pk if case else None, [document.pk for document in documents]))
            return 1

        result = send_document_reminder_for_client(
            client=self.client_obj,
            actor=None,
            send_email=fake_sender,
        )

        self.assertTrue(result.email_sent)
        self.assertEqual(result.affected_documents_count, 2)
        self.assertCountEqual(
            calls,
            [
                (self.case_a.pk, [document_a.pk]),
                (self.case_b.pk, [document_b.pk]),
            ],
        )
