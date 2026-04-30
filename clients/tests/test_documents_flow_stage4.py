from __future__ import annotations

from io import BytesIO
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from reportlab.pdfgen import canvas

from clients.constants import DocumentType
from clients.models import Client, Document, DocumentProcessingJob
from clients.services.document_workflow import enqueue_document_processing_job
from clients.services.roles import ensure_predefined_roles
from clients.services.wezwanie_parser import WezwanieData


def build_pdf_upload(name: str, text: str = "wezwanie test") -> SimpleUploadedFile:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, text)
    pdf.save()
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/pdf")


def _assign_staff_role(user, role_name: str = "Staff") -> None:
    ensure_predefined_roles()
    user.groups.add(Group.objects.get(name=role_name))


@override_settings(ASYNC_OCR_PROCESSING=True)
class DocumentFlowsStage4Tests(TestCase):
    def setUp(self):
        ensure_predefined_roles()
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(email="staff@example.com", password="pass", is_staff=True)
        _assign_staff_role(self.staff)
        self.client.login(email="staff@example.com", password="pass")
        self.client_obj = Client.objects.create(
            first_name="Anna",
            last_name="Nowak",
            citizenship="PL",
            phone="+48123123123",
            email="anna-stage4@example.com",
        )

    @patch("clients.views.documents.parse_wezwanie")
    def test_add_document_with_parse_requested_queues_confirmation_job(self, parse_mock):
        uploaded = build_pdf_upload("wezwanie.pdf")
        response = self.client.post(
            reverse(
                "clients:add_document",
                kwargs={"client_id": self.client_obj.pk, "doc_type": DocumentType.WEZWANIE.value},
            ),
            data={"file": uploaded, "parse_wezwanie": "1", "expiry_date": ""},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertFalse(payload["pending_confirmation"])
        self.assertTrue(payload["ocr_processing_queued"])
        self.assertIsNone(payload["parsed"])
        parse_mock.assert_not_called()

        document = Document.objects.get(client=self.client_obj)
        job = DocumentProcessingJob.objects.get(document=document)
        self.assertFalse(document.awaiting_confirmation)
        self.assertEqual(document.ocr_status, "pending")
        self.assertIsNone(document.parsed_data)
        self.assertTrue(job.requires_confirmation)
        self.assertEqual(job.status, DocumentProcessingJob.STATUS_PENDING)

    @override_settings(ASYNC_OCR_PROCESSING=False)
    @patch("clients.views.documents.parse_wezwanie")
    def test_add_document_with_inline_parse_returns_confirmation_payload(self, parse_mock):
        parse_mock.return_value = WezwanieData(
            text="parsed",
            case_number="WSC-II-S.123.2026",
            fingerprints_date=date(2030, 1, 5),
            full_name="Anna Nowak",
            wezwanie_type="fingerprints",
        )
        uploaded = build_pdf_upload("wezwanie-inline.pdf")

        response = self.client.post(
            reverse(
                "clients:add_document",
                kwargs={"client_id": self.client_obj.pk, "doc_type": DocumentType.WEZWANIE.value},
            ),
            data={"file": uploaded, "parse_wezwanie": "1", "expiry_date": ""},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertTrue(payload["pending_confirmation"])
        self.assertFalse(payload["ocr_processing_queued"])
        self.assertEqual(payload["parsed"]["case_number"], "WSC-II-S.123.2026")
        parse_mock.assert_called_once()

        document = Document.objects.get(client=self.client_obj, document_type=DocumentType.WEZWANIE.value)
        job = DocumentProcessingJob.objects.get(document=document)
        self.assertTrue(document.awaiting_confirmation)
        self.assertEqual(document.ocr_status, "success")
        self.assertEqual(job.status, DocumentProcessingJob.STATUS_COMPLETED)

    @patch("clients.management.commands.process_document_jobs.parse_wezwanie", side_effect=RuntimeError("ocr failed"))
    def test_confirmable_ocr_failure_is_handled_by_worker(self, _parse_mock):
        uploaded = build_pdf_upload("wezwanie.pdf")

        response = self.client.post(
            reverse(
                "clients:add_document",
                kwargs={"client_id": self.client_obj.pk, "doc_type": DocumentType.WEZWANIE.value},
            ),
            data={"file": uploaded, "parse_wezwanie": "1", "expiry_date": ""},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertFalse(payload["manual_review_required"])
        self.assertFalse(payload.get("pending_confirmation", False))
        self.assertTrue(payload["ocr_processing_queued"])
        self.assertEqual(Document.objects.filter(client=self.client_obj).count(), 1)

        document = Document.objects.get(client=self.client_obj)
        job = DocumentProcessingJob.objects.get(document=document)

        call_command("process_document_jobs")

        document.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(document.ocr_status, "failed")
        self.assertFalse(document.awaiting_confirmation)
        self.assertEqual(job.status, DocumentProcessingJob.STATUS_PENDING)
        self.assertEqual(job.attempts, 1)

    @patch("clients.management.commands.process_document_jobs.parse_wezwanie")
    def test_confirmable_ocr_empty_parse_result_marks_ocr_failed(self, parse_mock):
        parse_mock.return_value = WezwanieData(text="", error="no_text")
        uploaded = build_pdf_upload("wezwanie.pdf")

        response = self.client.post(
            reverse(
                "clients:add_document",
                kwargs={"client_id": self.client_obj.pk, "doc_type": DocumentType.WEZWANIE.value},
            ),
            data={"file": uploaded, "parse_wezwanie": "1", "expiry_date": ""},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertFalse(payload.get("manual_review_required", False))
        self.assertTrue(payload["ocr_processing_queued"])

        document = Document.objects.get(client=self.client_obj, document_type=DocumentType.WEZWANIE.value)
        job = DocumentProcessingJob.objects.get(document=document)

        call_command("process_document_jobs")

        document.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(document.ocr_status, "failed")
        self.assertFalse(document.awaiting_confirmation)
        self.assertEqual(job.status, DocumentProcessingJob.STATUS_PENDING)
        self.assertEqual(job.attempts, 1)

    def test_add_document_rejects_disallowed_file_type(self):
        uploaded = SimpleUploadedFile("wezwanie.svg", b"<svg></svg>", content_type="image/svg+xml")

        response = self.client.post(
            reverse(
                "clients:add_document",
                kwargs={"client_id": self.client_obj.pk, "doc_type": DocumentType.WEZWANIE.value},
            ),
            data={"file": uploaded, "parse_wezwanie": "1", "expiry_date": ""},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "error")
        self.assertEqual(Document.objects.filter(client=self.client_obj).count(), 0)

    def test_uploading_multiple_documents_preserves_both(self):
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file=SimpleUploadedFile("passport-old.pdf", b"old-data", content_type="application/pdf"),
        )

        response = self.client.post(
            reverse(
                "clients:add_document",
                kwargs={"client_id": self.client_obj.pk, "doc_type": DocumentType.PASSPORT.value},
            ),
            data={
                "file": build_pdf_upload("passport-new.pdf", text="passport replacement"),
                "expiry_date": "",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        
        docs = Document.objects.filter(client=self.client_obj, document_type=DocumentType.PASSPORT.value)
        self.assertEqual(docs.count(), 2)

    def test_uploading_document_succeeds_even_if_previous_file_is_missing(self):
        original = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file=SimpleUploadedFile("passport-missing.pdf", b"old-data", content_type="application/pdf"),
        )
        original.file.storage.delete(original.file.name)

        response = self.client.post(
            reverse(
                "clients:add_document",
                kwargs={"client_id": self.client_obj.pk, "doc_type": DocumentType.PASSPORT.value},
            ),
            data={
                "file": build_pdf_upload("passport-replacement.pdf", text="replacement after missing file"),
                "expiry_date": "",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        docs = Document.objects.filter(client=self.client_obj, document_type=DocumentType.PASSPORT.value)
        self.assertEqual(docs.count(), 2)

    def test_add_document_without_parse_requested_only_saves_document(self):
        uploaded = build_pdf_upload("wezwanie-background.pdf")

        response = self.client.post(
            reverse(
                "clients:add_document",
                kwargs={"client_id": self.client_obj.pk, "doc_type": DocumentType.WEZWANIE.value},
            ),
            data={"file": uploaded, "expiry_date": ""},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")

        document = Document.objects.get(client=self.client_obj, document_type=DocumentType.WEZWANIE.value)

        self.assertEqual(document.ocr_status, "skipped")
        self.assertFalse(document.awaiting_confirmation)
        self.assertFalse(DocumentProcessingJob.objects.filter(document=document).exists())

    @patch("clients.management.commands.process_document_jobs.send_appointment_notification_email", return_value=1)
    @patch("clients.management.commands.process_document_jobs.send_missing_documents_email", return_value=1)
    @patch("clients.management.commands.process_document_jobs.parse_wezwanie")
    def test_process_document_jobs_updates_client_and_marks_job_completed(
        self,
        parse_mock,
        _send_missing,
        _send_appointment,
    ):
        parse_mock.return_value = WezwanieData(
            text="parsed",
            case_number="WSC-II-S.123.2026",
            fingerprints_date=date(2030, 1, 5),
            full_name="Anna Nowak",
            wezwanie_type="fingerprints",
            required_documents=[DocumentType.PASSPORT.value],
        )

        document = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.WEZWANIE.value,
            file=build_pdf_upload("wezwanie-queued.pdf"),
        )
        job = enqueue_document_processing_job(document=document, actor=self.staff, requires_confirmation=False)

        call_command("process_document_jobs")

        self.client_obj.refresh_from_db()
        document.refresh_from_db()
        job.refresh_from_db()

        self.assertEqual(self.client_obj.case_number, "WSC-II-S.123.2026")
        self.assertEqual(self.client_obj.fingerprints_date, date(2030, 1, 5))
        self.assertEqual(document.ocr_status, "success")
        self.assertFalse(document.awaiting_confirmation)
        self.assertEqual(job.status, DocumentProcessingJob.STATUS_COMPLETED)
        self.assertEqual(job.attempts, 1)

    @patch("clients.management.commands.process_document_jobs.parse_wezwanie")
    def test_process_document_jobs_marks_job_failed_for_empty_parse_result(self, parse_mock):
        parse_mock.return_value = WezwanieData(text="", error="no_text")

        document = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.WEZWANIE.value,
            file=build_pdf_upload("wezwanie-empty.pdf"),
        )
        job = enqueue_document_processing_job(document=document, actor=self.staff, requires_confirmation=False)

        call_command("process_document_jobs")

        document.refresh_from_db()
        job.refresh_from_db()

        self.assertEqual(document.ocr_status, "failed")
        self.assertFalse(document.awaiting_confirmation)
        self.assertEqual(job.status, DocumentProcessingJob.STATUS_PENDING)
        self.assertEqual(job.attempts, 1)

    def test_confirm_wezwanie_parse_get_ajax_returns_405(self):
        document = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.WEZWANIE.value,
            file=SimpleUploadedFile("w.pdf", b"data", content_type="application/pdf"),
            awaiting_confirmation=True,
        )

        response = self.client.get(
            reverse("clients:confirm_wezwanie_parse", kwargs={"doc_id": document.pk}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["status"], "error")

    def test_confirm_wezwanie_parse_rejects_non_wezwanie_document(self):
        document = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file=SimpleUploadedFile("p.pdf", b"data", content_type="application/pdf"),
        )

        response = self.client.post(
            reverse("clients:confirm_wezwanie_parse", kwargs={"doc_id": document.pk}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "error")

    @patch("clients.views.documents.send_appointment_notification_email", return_value=1)
    @patch("clients.views.documents.send_missing_documents_email", return_value=1)
    @patch("clients.views.documents.parse_wezwanie")
    def test_confirm_wezwanie_parse_updates_client_and_clears_pending(
        self,
        parse_mock,
        _send_missing,
        _send_appointment,
    ):
        parse_mock.return_value = WezwanieData(
            text="parsed",
            required_documents=[DocumentType.PASSPORT.value],
            fingerprints_date=date(2030, 1, 5),
        )

        document = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.WEZWANIE.value,
            file=SimpleUploadedFile("w2.pdf", b"data", content_type="application/pdf"),
            awaiting_confirmation=True,
        )

        response = self.client.post(
            reverse("clients:confirm_wezwanie_parse", kwargs={"doc_id": document.pk}),
            data={
                "first_name": "Ann",
                "last_name": "Nowak",
                "case_number": "AB/123",
                "fingerprints_date": "2030-01-05",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")

        self.client_obj.refresh_from_db()
        document.refresh_from_db()
        self.assertEqual(self.client_obj.first_name, "Ann")
        self.assertEqual(self.client_obj.case_number, "AB/123")
        self.assertFalse(document.awaiting_confirmation)

    @patch("clients.views.documents.send_missing_documents_email", return_value=1)
    def test_toggle_document_verification_sends_email_only_on_first_verify(self, send_mock):
        document = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file=SimpleUploadedFile("doc.pdf", b"data", content_type="application/pdf"),
            verified=False,
        )

        response_1 = self.client.post(
            reverse("clients:toggle_document_verification", kwargs={"doc_id": document.pk}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response_1.status_code, 200)
        self.assertTrue(response_1.json()["verified"])
        self.assertTrue(response_1.json()["emails_sent"])

        response_2 = self.client.post(
            reverse("clients:toggle_document_verification", kwargs={"doc_id": document.pk}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response_2.status_code, 200)
        self.assertFalse(response_2.json()["verified"])
        self.assertFalse(response_2.json()["emails_sent"])

        self.assertEqual(send_mock.call_count, 1)
