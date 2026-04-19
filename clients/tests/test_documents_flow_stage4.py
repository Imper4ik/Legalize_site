from __future__ import annotations

from io import BytesIO
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from reportlab.pdfgen import canvas

from clients.constants import DocumentType
from clients.models import Client, Document
from clients.services.wezwanie_parser import WezwanieData


def build_pdf_upload(name: str, text: str = "wezwanie test") -> SimpleUploadedFile:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, text)
    pdf.save()
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/pdf")


class DocumentFlowsStage4Tests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(email="staff@example.com", password="pass", is_staff=True)
        self.client.login(email="staff@example.com", password="pass")
        self.client_obj = Client.objects.create(
            first_name="Anna",
            last_name="Nowak",
            citizenship="PL",
            phone="+48123123123",
            email="anna-stage4@example.com",
        )

    @patch("clients.views.documents.parse_wezwanie")
    def test_add_document_with_parse_requested_returns_pending_confirmation(self, parse_mock):
        parse_mock.return_value = WezwanieData(
            text="wezwanie text",
            case_number="WSC-II-S.1234.2025",
            fingerprints_date=date(2030, 1, 10),
            full_name="Anna Nowak",
        )

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
        self.assertTrue(payload["pending_confirmation"])

        document = Document.objects.get(client=self.client_obj)
        self.assertTrue(document.awaiting_confirmation)

    @patch("clients.views.documents.parse_wezwanie", side_effect=RuntimeError("ocr failed"))
    def test_add_document_with_parse_failure_keeps_document_and_flags_manual_review(self, _parse_mock):
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
        self.assertTrue(payload["manual_review_required"])
        self.assertFalse(payload.get("pending_confirmation", False))
        self.assertEqual(Document.objects.filter(client=self.client_obj).count(), 1)

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
