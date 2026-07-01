from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from clients.constants import DocumentType
from clients.models import DocumentProcessingJob, DocumentRequirement, EmailLog
from clients.services.case_context import checklist_for_case, purpose_for_case
from clients.services.cases import create_case_for_client
from clients.services.notifications import _get_missing_documents_context, send_expiring_documents_email
from clients.services.wniosek import create_wniosek_submission, get_submitted_document_codes
from clients.testing.factories import create_test_client, create_test_document


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

    def test_send_required_documents_email_scopes_to_case(self) -> None:
        from clients.models import ClientDocumentRequirement, DocumentRequirement, EmailLog
        from clients.services.notifications import send_required_documents_email

        # Create distinct requirements for work and study
        DocumentRequirement.objects.create(
            application_purpose="work",
            document_type="work_req",
            custom_name_en="Work Requirement",
            is_required=True,
        )
        DocumentRequirement.objects.create(
            application_purpose="study",
            document_type="study_req",
            custom_name_en="Study Requirement",
            is_required=True,
        )

        # Create custom requirement for case_a
        ClientDocumentRequirement.objects.create(
            client=self.client_obj,
            case=self.case_a,
            document_type="custom_a",
            name="Custom Req Case A",
            is_required=True,
            is_active=True,
        )
        # Create custom requirement for case_b
        ClientDocumentRequirement.objects.create(
            client=self.client_obj,
            case=self.case_b,
            document_type="custom_b",
            name="Custom Req Case B",
            is_required=True,
            is_active=True,
        )

        # 1. Send for Case A
        EmailLog.objects.all().delete()
        send_required_documents_email(self.client_obj, case=self.case_a)

        # Verify EmailLog was created, points to case_a, and has work_req & custom_a but NOT study_req & custom_b
        log_a = EmailLog.objects.get()
        self.assertEqual(log_a.case_id, self.case_a.pk)
        self.assertIn("Work Requirement", log_a.body)
        self.assertIn("Custom Req Case A", log_a.body)
        self.assertNotIn("Study Requirement", log_a.body)
        self.assertNotIn("Custom Req Case B", log_a.body)

        # 2. Send for Case B
        EmailLog.objects.all().delete()
        send_required_documents_email(self.client_obj, case=self.case_b)

        log_b = EmailLog.objects.get()
        self.assertEqual(log_b.case_id, self.case_b.pk)
        self.assertIn("Study Requirement", log_b.body)
        self.assertIn("Custom Req Case B", log_b.body)
        self.assertNotIn("Work Requirement", log_b.body)
        self.assertNotIn("Custom Req Case A", log_b.body)

        # Verify different idempotency keys are created (they contain case.pk)
        self.assertNotEqual(log_a.idempotency_key, log_b.idempotency_key)

        # 3. Test legacy calls without Case. Since client has multiple active cases, it must raise ValidationError
        with self.assertRaises(ValidationError):
            send_required_documents_email(self.client_obj)

        # If client has only one active case, legacy call should succeed.
        # Let's archive case_b so client has only one active case (case_a).
        self.case_b.archived_at = timezone.now()
        self.case_b.save()

        # Now legacy call should succeed and target case_a
        EmailLog.objects.all().delete()
        send_required_documents_email(self.client_obj)
        log_legacy = EmailLog.objects.get()
        self.assertEqual(log_legacy.case_id, self.case_a.pk)
