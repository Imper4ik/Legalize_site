from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from reportlab.pdfgen import canvas

from clients.constants import DocumentType
from clients.models import Client, Document, DocumentProcessingJob
from clients.services.document_workflow import reclaim_stale_document_jobs
from clients.services.wezwanie_parser import WezwanieData


def build_pdf_upload(name: str, text: str = "wezwanie test") -> SimpleUploadedFile:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, text)
    pdf.save()
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/pdf")


class DocumentJobsStage18Tests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(email="staff-stage18@example.com", password="pass", is_staff=True)
        self.client.force_login(self.staff)
        self.client_obj = Client.objects.create(
            first_name="Nadia",
            last_name="Melnik",
            citizenship="UA",
            phone="+48777777777",
            email="nadia-stage18@example.com",
        )

    def _queue_wezwanie_document(self):
        self.client.post(
            reverse(
                "clients:add_document",
                kwargs={"client_id": self.client_obj.pk, "doc_type": DocumentType.WEZWANIE.value},
            ),
            data={"file": build_pdf_upload("queued.pdf"), "expiry_date": ""},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        document = Document.objects.get(client=self.client_obj, document_type=DocumentType.WEZWANIE.value)
        job = DocumentProcessingJob.objects.get(document=document)
        return document, job

    @patch("clients.management.commands.process_document_jobs.parse_wezwanie")
    def test_empty_parse_result_requeues_job_with_backoff(self, parse_mock):
        parse_mock.return_value = WezwanieData(text="", error="no_text")
        document, job = self._queue_wezwanie_document()

        call_command("process_document_jobs")

        document.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(document.ocr_status, "failed")
        self.assertEqual(job.status, DocumentProcessingJob.STATUS_PENDING)
        self.assertEqual(job.attempts, 1)
        self.assertIsNotNone(job.next_attempt_at)
        self.assertIsNone(job.completed_at)

    @patch("clients.management.commands.process_document_jobs.parse_wezwanie")
    def test_job_becomes_terminal_failure_after_max_attempts(self, parse_mock):
        parse_mock.return_value = WezwanieData(text="", error="no_text")
        _document, job = self._queue_wezwanie_document()
        job.attempts = 2
        job.max_attempts = 3
        job.next_attempt_at = job.created_at - timedelta(seconds=1) if job.created_at else None
        job.save(update_fields=["attempts", "max_attempts", "next_attempt_at"])

        call_command("process_document_jobs")

        job.refresh_from_db()
        self.assertEqual(job.status, DocumentProcessingJob.STATUS_FAILED)
        self.assertEqual(job.attempts, 3)
        self.assertIsNotNone(job.completed_at)

    def test_reclaim_stale_processing_job_requeues_it(self):
        document = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.WEZWANIE.value,
            file=build_pdf_upload("stale.pdf"),
            ocr_status="pending",
        )
        job = DocumentProcessingJob.objects.create(
            document=document,
            created_by=self.staff,
            status=DocumentProcessingJob.STATUS_PROCESSING,
            source_file_name=document.file.name,
            attempts=1,
            max_attempts=3,
            lease_expires_at=document.uploaded_at - timedelta(minutes=1),
        )

        reclaimed = reclaim_stale_document_jobs()

        job.refresh_from_db()
        self.assertEqual(reclaimed, 1)
        self.assertEqual(job.status, DocumentProcessingJob.STATUS_PENDING)
        self.assertIsNone(job.lease_expires_at)

    @patch("clients.management.commands.process_document_jobs.send_appointment_notification_email", return_value=1)
    @patch("clients.management.commands.process_document_jobs.send_missing_documents_email", return_value=1)
    @patch("clients.management.commands.process_document_jobs.parse_wezwanie")
    def test_successful_job_clears_retry_metadata(self, parse_mock, _send_missing, _send_appointment):
        parse_mock.return_value = WezwanieData(
            text="parsed",
            case_number="WSC-II-S.555.2026",
            fingerprints_date=date(2030, 1, 5),
            full_name="Nadia Melnik",
            wezwanie_type="fingerprints",
        )
        _document, job = self._queue_wezwanie_document()

        call_command("process_document_jobs")

        job.refresh_from_db()
        self.assertEqual(job.status, DocumentProcessingJob.STATUS_COMPLETED)
        self.assertIsNone(job.next_attempt_at)
        self.assertIsNone(job.lease_expires_at)
