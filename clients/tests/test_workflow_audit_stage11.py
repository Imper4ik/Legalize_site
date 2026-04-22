from __future__ import annotations

import shutil
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from clients.constants import DocumentType
from clients.models import Client, ClientActivity, Document, DocumentVersion, EmailLog, StaffTask
from clients.services.responses import NO_STORE_HEADER


TEST_MEDIA_ROOT = Path(__file__).resolve().parents[2] / "generated_media_test" / "workflow_audit"
TEST_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class WorkflowAuditStage11Tests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(email="staff-stage11@example.com", password="pass", is_staff=True)
        self.client.force_login(self.staff)
        self.client_obj = Client.objects.create(
            first_name="Iryna",
            last_name="Koval",
            citizenship="UA",
            phone="+48123123123",
            email="iryna-stage11@example.com",
            legal_basis_end_date=timezone.localdate() + timedelta(days=7),
        )

    def test_client_detail_logs_view_and_exposes_workflow_summary(self):
        response = self.client.get(reverse("clients:client_detail", kwargs={"pk": self.client_obj.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            ClientActivity.objects.filter(client=self.client_obj, event_type="client_viewed").count(),
            1,
        )
        self.assertGreaterEqual(response.context["workflow_summary"]["alerts_count"], 1)

    def test_document_download_creates_activity(self):
        document = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.WEZWANIE.value,
            file=SimpleUploadedFile("wezwanie.pdf", b"pdf-data", content_type="application/pdf"),
        )

        response = self.client.get(reverse("clients:document_download", kwargs={"doc_id": document.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], NO_STORE_HEADER)
        self.assertTrue(
            ClientActivity.objects.filter(
                client=self.client_obj,
                event_type="document_downloaded",
                document=document,
            ).exists()
        )

    def test_add_and_complete_task_creates_timeline_entries(self):
        create_response = self.client.post(
            reverse("clients:add_task", kwargs={"client_id": self.client_obj.pk}),
            data={
                "title": "Call client",
                "description": "Clarify missing passport pages",
                "priority": "high",
                "status": "open",
                "due_date": timezone.localdate().isoformat(),
            },
        )

        self.assertEqual(create_response.status_code, 302)
        task = StaffTask.objects.get(client=self.client_obj)
        self.assertEqual(task.status, "open")
        self.assertTrue(
            ClientActivity.objects.filter(client=self.client_obj, event_type="task_created", task=task).exists()
        )

        complete_response = self.client.post(reverse("clients:complete_task", kwargs={"task_id": task.pk}))

        self.assertEqual(complete_response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, "done")
        self.assertIsNotNone(task.completed_at)
        self.assertTrue(
            ClientActivity.objects.filter(client=self.client_obj, event_type="task_completed", task=task).exists()
        )

    def test_email_log_signal_creates_activity(self):
        EmailLog.objects.create(
            client=self.client_obj,
            subject="Appointment notification",
            body="Body",
            recipients=self.client_obj.email,
            template_type="appointment_notification",
            sent_by=self.staff,
        )

        self.assertTrue(
            ClientActivity.objects.filter(client=self.client_obj, event_type="email_sent").exists()
        )

    def test_client_export_zip_creates_export_audit_event(self):
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file=SimpleUploadedFile("passport.pdf", b"pdf-data", content_type="application/pdf"),
        )

        response = self.client.get(reverse("clients:client_export_zip", kwargs={"pk": self.client_obj.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], NO_STORE_HEADER)
        activity = ClientActivity.objects.filter(
            client=self.client_obj,
            event_type="client_exported",
        ).first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.metadata["export_type"], "zip")

    def test_document_version_restore_creates_specific_audit_event(self):
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

        response = self.client.post(reverse("clients:document_version_restore", kwargs={"version_id": version.pk}))

        self.assertEqual(response.status_code, 302)
        activity = ClientActivity.objects.filter(
            client=self.client_obj,
            event_type="document_version_restored",
            document=document,
        ).first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.metadata["restored_version_id"], version.pk)
        self.assertEqual(activity.metadata["restored_version_number"], 1)

    def test_document_version_download_uses_authorized_endpoint_and_logs_event(self):
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

        response = self.client.get(
            reverse("clients:document_version_download", kwargs={"version_id": version.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], NO_STORE_HEADER)
        activity = ClientActivity.objects.filter(
            client=self.client_obj,
            event_type="client_exported",
            metadata__document_version_id=version.pk,
        ).first()
        self.assertIsNotNone(activity)
