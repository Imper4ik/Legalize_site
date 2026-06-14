from __future__ import annotations

from datetime import date
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

from clients.constants import WEZWANIE_DOCUMENT_TYPES, DocumentType
from clients.models import Client, Document, DocumentProcessingJob
from clients.services.document_workflow import enqueue_document_processing_job, process_document_processing_job
from clients.services.roles import ensure_predefined_roles
from clients.services.wezwanie_parser import WezwanieData, parse_wezwanie


def build_pdf_upload(name: str, text: str = "wezwanie test") -> SimpleUploadedFile:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, text)
    pdf.save()
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/pdf")


@override_settings(ASYNC_OCR_PROCESSING=True)
class WezwanieOCRStage19Tests(TestCase):
    def setUp(self):
        ensure_predefined_roles()
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(email="staff-ocr@example.com", password="pass", is_staff=True, is_superuser=True)
        self.client.login(email="staff-ocr@example.com", password="pass")
        self.client_obj = Client.objects.create(
            first_name="Darya",
            last_name="Afanasenka",
            citizenship="BY",
            phone="+48000000000",
            email="darya@example.com",
            application_purpose="work"
        )

    def test_wezwanie_document_types_constant(self):
        self.assertIn("wezwanie", WEZWANIE_DOCUMENT_TYPES)
        self.assertIn("fingerprint_confirmation", WEZWANIE_DOCUMENT_TYPES)
        self.assertIn("formal_deficiencies", WEZWANIE_DOCUMENT_TYPES)
        self.assertIn("braki_formalne", WEZWANIE_DOCUMENT_TYPES)

    @patch("clients.management.commands.process_document_jobs.send_appointment_notification_email", return_value=0)
    @patch("clients.management.commands.process_document_jobs.send_missing_documents_email", return_value=0)
    @patch("clients.management.commands.process_document_jobs.parse_wezwanie")
    def test_upload_confirmable_ocr_queues_job_then_worker_saves_ticket_data(
        self,
        parse_mock,
        _send_missing,
        _send_appointment,
    ):
        parse_mock.return_value = WezwanieData(
            text="sample text",
            full_name="Darya AFANASENKA",
            case_number="WSC-II-P.6151.138285.2025",
            fingerprints_date=date(2026, 5, 4),
            fingerprints_time="10:30",
            wezwanie_type="fingerprints",
            fingerprints_location="Marszałkowska 3/5",
            ticket_number="X29",
            list_name="Lista X1",
            application_status_code="P",
            decision_date=None,
            required_documents=[]
        )

        uploaded = build_pdf_upload("new_wezwanie.pdf")
        response = self.client.post(
            reverse("clients:add_document", kwargs={"client_id": self.client_obj.pk, "doc_type": "formal_deficiencies"}),
            data={"file": uploaded, "parse_wezwanie": "1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertFalse(payload["pending_confirmation"])
        self.assertTrue(payload["ocr_processing_queued"])
        self.assertIsNone(payload["parsed"])

        doc = Document.objects.get(client=self.client_obj, document_type="formal_deficiencies")
        job = DocumentProcessingJob.objects.get(document=doc)
        self.assertEqual(doc.ocr_status, "pending")
        self.assertFalse(doc.awaiting_confirmation)
        self.assertTrue(job.requires_confirmation)

        call_command("process_document_jobs")

        doc.refresh_from_db()
        self.client_obj.refresh_from_db()
        self.assertEqual(doc.ocr_status, "success")
        self.assertTrue(doc.awaiting_confirmation)
        self.assertEqual(doc.parsed_data["case_number"], "WSC-II-P.6151.138285.2025")
        self.assertEqual(doc.parsed_data["fingerprints_date_display"], "04.05.2026")
        self.assertEqual(doc.parsed_data["ticket_number"], "X29")
        self.assertEqual(doc.parsed_data["list_name"], "Lista X1")
        self.assertIsNone(self.client_obj.fingerprints_ticket)
        self.assertIsNone(self.client_obj.fingerprints_list)
        _send_missing.assert_not_called()
        _send_appointment.assert_not_called()

    def test_background_ocr_saves_ticket_and_list_in_document_parsed_data(self):
        document = Document.objects.create(
            client=self.client_obj,
            document_type="wezwanie",
            file=build_pdf_upload("queued_wezwanie.pdf"),
        )
        job = enqueue_document_processing_job(document=document, actor=self.staff)

        parsed = WezwanieData(
            text="bilet X29 Lista X1",
            full_name="Darya AFANASENKA",
            case_number="WSC-II-P.6151.138285.2025",
            fingerprints_date=date(2026, 5, 4),
            fingerprints_time="10:30",
            wezwanie_type="fingerprints",
            fingerprints_location="Marszałkowska 3/5, pok. 14,16, stan. 10,11",
            ticket_number="X29",
            list_name="Lista X1",
            application_status_code="P",
        )

        result = process_document_processing_job(
            job_id=job.pk,
            parser=lambda _path: parsed,
            send_missing_email=lambda _client: 0,
            send_appointment_email=lambda _client: 0,
        )

        self.assertEqual(result.status, DocumentProcessingJob.STATUS_COMPLETED)
        document.refresh_from_db()
        self.client_obj.refresh_from_db()
        self.assertEqual(document.parsed_data["ticket_number"], "X29")
        self.assertEqual(document.parsed_data["list_name"], "Lista X1")
        self.assertEqual(self.client_obj.fingerprints_ticket, "X29")
        self.assertEqual(self.client_obj.fingerprints_list, "Lista X1")

        self.assertTrue(document.parsed_data.get("pii_scrubbed"))
        self.assertNotIn("full_name", document.parsed_data)
        self.assertNotIn("first_name", document.parsed_data)
        self.assertNotIn("last_name", document.parsed_data)
        self.assertNotIn("case_number", document.parsed_data)
        self.assertNotIn("text", document.parsed_data)
        self.assertNotIn("raw_text", document.parsed_data)
        self.assertIn("application_status_code", document.parsed_data)
        self.assertIn("fingerprints_date", document.parsed_data)

    def test_upload_without_parse_request_only_saves_document(self):
        uploaded = build_pdf_upload("bg_wezwanie.pdf")
        response = self.client.post(
            reverse("clients:add_document", kwargs={"client_id": self.client_obj.pk, "doc_type": "wezwanie"}),
            data={"file": uploaded, "parse_wezwanie": "0"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload.get("pending_confirmation", False))

        doc = Document.objects.get(client=self.client_obj, document_type="wezwanie")
        self.assertEqual(doc.ocr_status, "skipped")
        self.assertFalse(DocumentProcessingJob.objects.filter(document=doc).exists())

    def test_parser_extracts_correct_fingerprint_date_and_time(self):
        # Sample text representing the new document type
        text = """
        Warszawa, dnia 23.04.2026 r.

        INFORMACJA O TERMINIE UZUPEŁNIENIA BRAKÓW FORMALNYCH WNIOSKU ORAZ ZŁOŻENIA ODCISKÓW LINII PAPILARNYCH

        Pan/i Darya AFANASENKA
        Numer sprawy: WSC-II-P.6151.138285.2025

        Termin został wyznaczony na dzień i godzinę: 4.05.2026, 10:30
        Miejsce: Marszałkowska 3/5, pok. 14,16, stanowisko 10,11
        Bilet: X29
        Lista X1

        Prosimy zabrać: paszport, 4 zdjęcia, załącznik nr 1, opłata skarbowa 440 zł.
        """

        # We need to mock extract_text because we are passing a fake path
        with patch("clients.services.wezwanie_parser.extract_text", return_value=text):
            data = parse_wezwanie("fake_path.pdf")

            self.assertEqual(data.wezwanie_type, "fingerprints")
            self.assertEqual(data.full_name, "Darya AFANASENKA")
            self.assertEqual(data.case_number, "WSC-II-P.6151.138285.2025")
            # Should NOT be 2026-04-23
            self.assertEqual(data.fingerprints_date, date(2026, 5, 4))
            self.assertEqual(data.fingerprints_time, "10:30")
            self.assertIn("Marszałkowska 3/5", data.fingerprints_location)
            self.assertEqual(data.ticket_number, "X29")
            self.assertEqual(data.list_name, "Lista X1")

            # Check required documents
            self.assertIn(DocumentType.PASSPORT.value, data.required_documents)
            self.assertIn(DocumentType.PHOTOS.value, data.required_documents)
            self.assertIn(DocumentType.ZALACZNIK_NR_1.value, data.required_documents)
            self.assertIn(DocumentType.PAYMENT_CONFIRMATION.value, data.required_documents)

    def test_is_wezwanie_document_type_helper(self):
        from clients.constants import is_wezwanie_document_type
        self.assertTrue(is_wezwanie_document_type("wezwanie"))
        self.assertTrue(is_wezwanie_document_type("WEZWANIE"))
        self.assertTrue(is_wezwanie_document_type("formal_deficiencies"))
        self.assertTrue(is_wezwanie_document_type("braki_formalne"))
        self.assertFalse(is_wezwanie_document_type("passport"))
        self.assertFalse(is_wezwanie_document_type(None))

    def test_parser_handles_weird_unicode_separator(self):
        # The user mentioned \ufffe as a common issue in case numbers
        text = "Numer sprawy: WSC-II\ufffeP.6151.138285.2025"
        with patch("clients.services.wezwanie_parser.extract_text", return_value=text):
            data = parse_wezwanie("fake.pdf")
            self.assertEqual(data.case_number, "WSC-II-P.6151.138285.2025")

    def test_parser_with_alternate_date_time_format(self):
        text = "dzień i godzinę: 12.12.2025r. godz. 09:15"
        with patch("clients.services.wezwanie_parser.extract_text", return_value=text):
            data = parse_wezwanie("fake.pdf")
            self.assertEqual(data.fingerprints_date, date(2025, 12, 12))
            self.assertEqual(data.fingerprints_time, "09:15")
