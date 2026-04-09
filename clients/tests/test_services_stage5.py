from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from clients.constants import DocumentType
from clients.models import Client, Document, DocumentRequirement
from clients.services import notifications
from clients.services.wezwanie_parser import (
    _detect_wezwanie_type,
    _extract_required_documents,
    _parse_date,
    parse_wezwanie,
)


class NotificationServiceStage5Tests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(email="u@example.com", password="pass")
        self.client_obj = Client.objects.create(
            first_name="Ira",
            last_name="Kowalska",
            citizenship="PL",
            phone="+48111111111",
            email="ira@example.com",
            application_purpose="work",
            language="pl",
            user=None,
        )

    def test_get_appointment_context_returns_none_without_date(self):
        self.client_obj.fingerprints_date = None
        self.client_obj.save(update_fields=["fingerprints_date"])

        context = notifications._get_appointment_context(self.client_obj)

        self.assertIsNone(context)

    def test_send_appointment_notification_returns_zero_without_email(self):
        self.client_obj.email = ""
        self.client_obj.fingerprints_date = timezone.localdate()
        self.client_obj.save(update_fields=["email", "fingerprints_date"])

        sent = notifications.send_appointment_notification_email(self.client_obj)

        self.assertEqual(sent, 0)

    @patch("clients.services.notifications._send_email", return_value=1)
    def test_send_missing_documents_email_uses_send_email_when_missing_exists(self, send_mock):
        DocumentRequirement.objects.filter(application_purpose="work").delete()
        DocumentRequirement.objects.create(
            application_purpose="work",
            document_type=DocumentType.PASSPORT.value,
            is_required=True,
            position=0,
        )

        sent = notifications.send_missing_documents_email(self.client_obj)

        self.assertEqual(sent, 1)
        send_mock.assert_called_once()

    def test_get_missing_documents_context_returns_none_when_all_uploaded(self):
        DocumentRequirement.objects.filter(application_purpose="work").delete()
        DocumentRequirement.objects.create(
            application_purpose="work",
            document_type=DocumentType.PASSPORT.value,
            is_required=True,
            position=0,
        )
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file=SimpleUploadedFile("pass.pdf", b"x", content_type="application/pdf"),
        )

        context = notifications._get_missing_documents_context(self.client_obj, language="pl")

        self.assertIsNone(context)

    def test_get_expiring_documents_context_splits_documents_by_deadline(self):
        today = timezone.localdate()
        expired_doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file=SimpleUploadedFile("exp.pdf", b"x", content_type="application/pdf"),
            expiry_date=today - timedelta(days=1),
        )
        soon_doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PHOTOS.value,
            file=SimpleUploadedFile("soon.pdf", b"x", content_type="application/pdf"),
            expiry_date=today + timedelta(days=2),
        )
        later_doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.HEALTH_INSURANCE.value,
            file=SimpleUploadedFile("later.pdf", b"x", content_type="application/pdf"),
            expiry_date=today + timedelta(days=5),
        )

        context = notifications._get_expiring_documents_context(
            self.client_obj, [expired_doc, soon_doc, later_doc]
        )

        self.assertIsNotNone(context)
        self.assertEqual(len(context["expired_documents"]), 1)
        self.assertEqual(len(context["expiring_soon_documents"]), 1)
        self.assertEqual(len(context["expiring_later_documents"]), 1)


class WezwanieParserStage5Tests(TestCase):
    def test_parse_date_supports_multiple_formats(self):
        self.assertEqual(_parse_date("01.02.2030").isoformat(), "2030-02-01")
        self.assertEqual(_parse_date("2030-02-01").isoformat(), "2030-02-01")
        self.assertIsNone(_parse_date("not-a-date"))

    def test_detect_wezwanie_type(self):
        self.assertEqual(_detect_wezwanie_type("wezwanie na odciski palców"), "fingerprints")
        self.assertEqual(_detect_wezwanie_type("termin wydania decyzji"), "decision")
        self.assertEqual(_detect_wezwanie_type("potwierdzenie złożenia odcisków"), "confirmation")

    def test_extract_required_documents_detects_known_patterns(self):
        text = "Prosimy o dostarczenie 4 zdjęcia oraz kopia paszportu i opłata skarbowa."
        docs = _extract_required_documents(text)

        self.assertIn(DocumentType.PHOTOS.value, docs)
        self.assertIn(DocumentType.PASSPORT.value, docs)
        self.assertIn(DocumentType.PAYMENT_CONFIRMATION.value, docs)

    @patch("clients.services.wezwanie_parser.extract_text", return_value="")
    def test_parse_wezwanie_returns_no_text_error(self, _extract_text):
        parsed = parse_wezwanie("/tmp/missing.pdf")

        self.assertEqual(parsed.error, "no_text")
        self.assertEqual(parsed.text, "")

    @patch(
        "clients.services.wezwanie_parser.extract_text",
        return_value="WSC-II-S.6151.97770.2023 Odciski palców dnia 10.12.2030",
    )
    def test_parse_wezwanie_extracts_type_case_and_date(self, _extract_text):
        parsed = parse_wezwanie("/tmp/wezwanie.pdf")

        self.assertEqual(parsed.wezwanie_type, "fingerprints")
        self.assertTrue(parsed.case_number)
        self.assertIsNotNone(parsed.fingerprints_date)
