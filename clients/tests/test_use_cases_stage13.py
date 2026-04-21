from __future__ import annotations

import shutil
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from clients.constants import DocumentType
from clients.models import Client, ClientActivity, Document, DocumentVersion, WniosekAttachment, WniosekSubmission
from clients.use_cases.documents import (
    delete_client_document,
    delete_wniosek_attachment,
    record_document_download,
    toggle_client_document_verification,
    update_client_notes_for_client,
    verify_all_client_documents,
)
from clients.use_cases.exports import (
    record_client_export,
    restore_document_version_for_client,
)
from clients.use_cases.tasks import complete_task_for_client, create_task_for_client


TEST_MEDIA_ROOT = Path(__file__).resolve().parents[2] / "generated_media_test" / "use_cases_stage13"
TEST_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class UseCasesStage13Tests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            email="staff-stage13@example.com",
            password="pass",
            is_staff=True,
        )
        self.client_obj = Client.objects.create(
            first_name="Kateryna",
            last_name="Melnyk",
            citizenship="UA",
            phone="+48222222222",
            email="kateryna-stage13@example.com",
            legal_basis_end_date=timezone.localdate() + timedelta(days=20),
        )

    def test_update_client_notes_for_client_saves_notes_and_logs_activity(self):
        result = update_client_notes_for_client(
            client=self.client_obj,
            actor=self.staff,
            notes="Need to collect missing insurance papers.",
        )

        self.client_obj.refresh_from_db()
        self.assertEqual(result.notes, "Need to collect missing insurance papers.")
        self.assertEqual(self.client_obj.notes, "Need to collect missing insurance papers.")
        self.assertTrue(
            ClientActivity.objects.filter(
                client=self.client_obj,
                actor=self.staff,
                event_type="note_updated",
            ).exists()
        )

    def test_delete_client_document_removes_document_and_creates_audit_entry(self):
        document = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file=SimpleUploadedFile("passport.pdf", b"passport-data", content_type="application/pdf"),
        )

        result = delete_client_document(document=document, actor=self.staff)

        self.assertEqual(result.deleted_document_id, document.pk)
        self.assertFalse(Document.objects.filter(pk=document.pk).exists())
        activity = ClientActivity.objects.get(client=self.client_obj, event_type="document_deleted")
        self.assertEqual(activity.metadata["document_id"], document.pk)
        self.assertEqual(activity.metadata["document_type"], DocumentType.PASSPORT.value)

    def test_toggle_client_document_verification_sends_email_only_when_switching_to_verified(self):
        document = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file=SimpleUploadedFile("passport-verify.pdf", b"verify", content_type="application/pdf"),
            verified=False,
        )
        send_missing_email = Mock(return_value=1)

        first_result = toggle_client_document_verification(
            document=document,
            actor=self.staff,
            send_missing_email=send_missing_email,
        )
        second_result = toggle_client_document_verification(
            document=document,
            actor=self.staff,
            send_missing_email=send_missing_email,
        )

        self.assertTrue(first_result.verified)
        self.assertTrue(first_result.emails_sent)
        self.assertFalse(second_result.verified)
        self.assertFalse(second_result.emails_sent)
        self.assertEqual(send_missing_email.call_count, 1)
        self.assertEqual(
            ClientActivity.objects.filter(client=self.client_obj, event_type="document_verified").count(),
            2,
        )

    def test_verify_all_client_documents_marks_only_unverified_documents(self):
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file=SimpleUploadedFile("passport-a.pdf", b"a", content_type="application/pdf"),
            verified=False,
        )
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.HEALTH_INSURANCE.value,
            file=SimpleUploadedFile("insurance-b.pdf", b"b", content_type="application/pdf"),
            verified=False,
        )
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PAYMENT_CONFIRMATION.value,
            file=SimpleUploadedFile("permit-c.pdf", b"c", content_type="application/pdf"),
            verified=True,
        )
        send_missing_email = Mock(return_value=1)

        result = verify_all_client_documents(
            client=self.client_obj,
            actor=self.staff,
            send_missing_email=send_missing_email,
        )

        self.assertEqual(result.updated_count, 2)
        self.assertTrue(result.emails_sent)
        self.assertEqual(self.client_obj.documents.filter(verified=False).count(), 0)
        send_missing_email.assert_called_once_with(self.client_obj)
        activity = ClientActivity.objects.get(client=self.client_obj, event_type="document_verified")
        self.assertEqual(activity.metadata["verified_count"], 2)

    def test_delete_wniosek_attachment_updates_submission_count_and_logs_activity(self):
        submission = WniosekSubmission.objects.create(
            client=self.client_obj,
            attachment_count=2,
            confirmed_by=self.staff,
        )
        retained = WniosekAttachment.objects.create(
            submission=submission,
            document_type=DocumentType.PASSPORT.value,
            entered_name="Passport",
            position=0,
        )
        removable = WniosekAttachment.objects.create(
            submission=submission,
            document_type="",
            entered_name="Custom appendix",
            position=1,
        )

        result = delete_wniosek_attachment(attachment=removable, actor=self.staff)

        submission.refresh_from_db()
        self.assertEqual(result.remaining_count, 1)
        self.assertFalse(result.submission_deleted)
        self.assertEqual(submission.attachment_count, 1)
        self.assertFalse(WniosekAttachment.objects.filter(pk=removable.pk).exists())
        self.assertTrue(WniosekAttachment.objects.filter(pk=retained.pk).exists())
        activity = ClientActivity.objects.get(client=self.client_obj, event_type="wniosek_attachment_deleted")
        self.assertEqual(activity.metadata["attachment_id"], removable.pk)
        self.assertEqual(activity.metadata["remaining_count"], 1)

    def test_delete_last_wniosek_attachment_removes_submission(self):
        submission = WniosekSubmission.objects.create(
            client=self.client_obj,
            attachment_count=1,
            confirmed_by=self.staff,
        )
        attachment = WniosekAttachment.objects.create(
            submission=submission,
            document_type="",
            entered_name="Only appendix",
            position=0,
        )

        result = delete_wniosek_attachment(attachment=attachment, actor=self.staff)

        self.assertTrue(result.submission_deleted)
        self.assertFalse(WniosekAttachment.objects.filter(pk=attachment.pk).exists())
        self.assertFalse(WniosekSubmission.objects.filter(pk=submission.pk).exists())

    def test_record_document_download_creates_download_activity(self):
        document = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file=SimpleUploadedFile("passport-download.pdf", b"download", content_type="application/pdf"),
        )

        result = record_document_download(document=document, actor=self.staff)

        self.assertEqual(result.document, document)
        self.assertTrue(
            ClientActivity.objects.filter(
                client=self.client_obj,
                actor=self.staff,
                event_type="document_downloaded",
                document=document,
            ).exists()
        )

    def test_record_client_export_creates_export_activity_with_metadata(self):
        result = record_client_export(
            client=self.client_obj,
            actor=self.staff,
            export_type="zip",
            metadata={"document_count": 3},
            summary="Экспорт кейса (ZIP)",
        )

        self.assertEqual(result.export_type, "zip")
        activity = ClientActivity.objects.get(client=self.client_obj, event_type="client_exported")
        self.assertEqual(activity.metadata["export_type"], "zip")
        self.assertEqual(activity.metadata["document_count"], 3)

    def test_restore_document_version_for_client_restores_file_and_logs_activity(self):
        document = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file=SimpleUploadedFile("passport-current.pdf", b"current", content_type="application/pdf"),
        )
        version = DocumentVersion.objects.create(
            document=document,
            file=SimpleUploadedFile("passport-old.pdf", b"old", content_type="application/pdf"),
            version_number=1,
            file_name="passport-old.pdf",
            file_size=3,
            uploaded_by=self.staff,
        )

        result = restore_document_version_for_client(version=version, actor=self.staff)

        result.document.file.open("rb")
        try:
            restored_content = result.document.file.read()
        finally:
            result.document.file.close()

        self.assertEqual(restored_content, b"old")
        activity = ClientActivity.objects.get(client=self.client_obj, event_type="document_version_restored")
        self.assertEqual(activity.document, result.document)
        self.assertEqual(activity.metadata["restored_version_id"], version.pk)
        self.assertEqual(activity.metadata["restored_version_number"], 1)

    def test_create_task_for_client_creates_task_with_default_assignee_and_audit(self):
        due_date = timezone.localdate() + timedelta(days=2)

        result = create_task_for_client(
            client=self.client_obj,
            actor=self.staff,
            cleaned_data={
                "title": "Call client",
                "description": "Clarify passport scan quality.",
                "due_date": due_date,
                "priority": "high",
                "status": "open",
                "assignee": None,
                "document": None,
                "payment": None,
            },
        )

        self.assertTrue(result.created)
        self.assertEqual(result.task.assignee, self.staff)
        self.assertEqual(result.task.created_by, self.staff)
        activity = ClientActivity.objects.get(client=self.client_obj, event_type="task_created")
        self.assertEqual(activity.task, result.task)
        self.assertEqual(activity.metadata["priority"], "high")

    def test_complete_task_for_client_marks_task_done_once_and_logs_audit(self):
        task_result = create_task_for_client(
            client=self.client_obj,
            actor=self.staff,
            cleaned_data={
                "title": "Prepare checklist",
                "description": "",
                "due_date": None,
                "priority": "medium",
                "status": "open",
                "assignee": self.staff,
                "document": None,
                "payment": None,
            },
        )

        first_result = complete_task_for_client(task=task_result.task, actor=self.staff)
        second_result = complete_task_for_client(task=task_result.task, actor=self.staff)

        task_result.task.refresh_from_db()
        self.assertTrue(first_result.completed)
        self.assertFalse(second_result.completed)
        self.assertEqual(task_result.task.status, "done")
        self.assertIsNotNone(task_result.task.completed_at)
        self.assertEqual(
            ClientActivity.objects.filter(client=self.client_obj, event_type="task_completed", task=task_result.task).count(),
            1,
        )
