from __future__ import annotations

import json
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import get_template
from django.test import TestCase
from django.urls import reverse
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

from clients.constants import DocumentType
from clients.models import Client, Document, DocumentProcessingJob, DocumentRequirement, EmployeePermission
from clients.services.document_workflow import confirm_wezwanie_document, upload_client_document
from clients.services.roles import ensure_predefined_roles
from clients.use_cases.documents import verify_all_client_documents


def _pdf_upload(name: str, text: str = "test document") -> SimpleUploadedFile:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, text)
    pdf.save()
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/pdf")


def _assign_role(user, role_name: str = "Staff") -> None:
    ensure_predefined_roles()
    user.groups.add(Group.objects.get(name=role_name))


class DocumentOCRRegressionTests(TestCase):
    def setUp(self):
        ensure_predefined_roles()
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(email="ocr-regression@example.com", password="pass", is_staff=True)
        _assign_role(self.staff)
        self.client_record = Client.objects.create(
            first_name="Anna",
            last_name="Nowak",
            citizenship="PL",
            phone="+48123123123",
            email="anna-ocr-regression@example.com",
            application_purpose="work",
        )

    def test_client_modals_template_is_current(self):
        template = get_template("clients/partials/modals.html")
        source = template.template.source

        self.assertIn("wezwanieParsedTicketNumber", source)
        self.assertIn("wezwanieParsedListName", source)
        self.assertIn("wezwanieParsedStatusCode", source)
        self.assertIn("multiple", source)

    def test_uploaded_document_outside_required_checklist_is_visible(self):
        DocumentRequirement.objects.filter(application_purpose="work").delete()
        document = Document.objects.create(
            client=self.client_record,
            document_type="unexpected_uploaded_document",
            file=SimpleUploadedFile("extra.pdf", b"file"),
            awaiting_confirmation=True,
        )

        checklist = self.client_record.get_document_checklist()
        matching_items = [item for item in checklist if item["code"] == document.document_type]

        self.assertEqual(len(matching_items), 1)
        self.assertEqual(matching_items[0]["documents"], [document])

    def test_verify_all_files_clears_ocr_confirmation(self):
        document = Document.objects.create(
            client=self.client_record,
            document_type=DocumentType.WEZWANIE.value,
            file=SimpleUploadedFile("wezwanie.pdf", b"file"),
            verified=False,
            awaiting_confirmation=True,
        )

        result = verify_all_client_documents(
            client=self.client_record,
            actor=self.staff,
            send_missing_email=lambda _client: 0,
        )

        document.refresh_from_db()
        self.assertEqual(result.updated_count, 1)
        self.assertTrue(document.verified)
        self.assertFalse(document.awaiting_confirmation)

    def test_upload_wezwanie_without_parse_request_does_not_enqueue_ocr(self):
        parser = Mock(side_effect=AssertionError("parser must not run"))
        result = upload_client_document(
            client=self.client_record,
            doc_type=DocumentType.WEZWANIE.value,
            uploaded_document=Document(file=SimpleUploadedFile("wezwanie.pdf", b"file")),
            actor=self.staff,
            parse_requested=False,
            parser=parser,
            send_missing_email=lambda _client: 0,
            send_appointment_email=lambda _client: 0,
        )

        result.document.refresh_from_db()
        self.client_record.refresh_from_db()
        parser.assert_not_called()
        self.assertFalse(DocumentProcessingJob.objects.filter(document=result.document).exists())
        self.assertFalse(result.document.awaiting_confirmation)
        self.assertEqual(result.document.ocr_status, "skipped")
        self.assertIsNone(self.client_record.case_number)

    def test_confirm_ocr_uses_confirmed_data_without_rerunning_parser(self):
        document = Document.objects.create(
            client=self.client_record,
            document_type=DocumentType.WEZWANIE.value,
            file=SimpleUploadedFile("wezwanie.pdf", b"file"),
            awaiting_confirmation=True,
            ocr_status="success",
            parsed_data={
                "raw_text": "sensitive OCR text",
                "case_number": "OLD",
                "required_documents": [DocumentType.PHOTOS.value],
            },
        )
        parser = Mock(side_effect=RuntimeError("OCR parser unavailable"))

        result = confirm_wezwanie_document(
            document=document,
            actor=self.staff,
            confirmation_data={
                "case_number": "WSC-II-P.123.2026",
                "fingerprints_date": "2026-05-04",
            },
            parser=parser,
            send_missing_email=lambda _client: 0,
            send_appointment_email=lambda _client: 0,
        )

        document.refresh_from_db()
        self.client_record.refresh_from_db()
        parser.assert_not_called()
        self.assertFalse(result.manual_review_required)
        self.assertFalse(document.awaiting_confirmation)
        self.assertEqual(document.ocr_status, "success")
        # Process data is written to the document's Case, never the Client.
        case = document.case
        case.refresh_from_db()
        self.assertEqual(case.authority_case_number, "WSC-II-P.123.2026")
        self.assertEqual(case.fingerprints_date, date(2026, 5, 4))
        self.assertNotIn("raw_text", document.parsed_data)
        self.assertEqual(document.parsed_data["confirmed"], True)

    def test_staff_role_can_access_parsed_ocr_data_without_feature_flag(self):
        document = Document.objects.create(
            client=self.client_record,
            document_type=DocumentType.WEZWANIE.value,
            file=SimpleUploadedFile("wezwanie.pdf", b"file"),
            awaiting_confirmation=True,
            parsed_data={"case_number": "WSC-II-P.123.2026"},
        )
        url = reverse("clients:get_document_parsed_data", kwargs={"doc_id": document.pk})

        self.client.force_login(self.staff)
        response = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["parsed_data"]["case_number"], "WSC-II-P.123.2026")

        reviewer = get_user_model().objects.create_user(
            email="ocr-reviewer@example.com",
            password="pass",
            is_staff=True,
        )
        _assign_role(reviewer)
        EmployeePermission.objects.update_or_create(
            user=reviewer,
            defaults={"can_run_ocr_review": True},
        )
        self.client.force_login(reviewer)
        response = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["parsed_data"]["case_number"], "WSC-II-P.123.2026")

        other_staff = get_user_model().objects.create_user(
            email="other-reviewer@example.com",
            password="pass",
            is_staff=True,
        )
        _assign_role(other_staff)
        EmployeePermission.objects.update_or_create(
            user=other_staff,
            defaults={"can_run_ocr_review": True},
        )
        restricted_client = Client.objects.create(
            first_name="Restricted",
            last_name="Case",
            citizenship="PL",
            phone="+48000000000",
            email="restricted@example.com",
            assigned_staff=self.staff,
        )
        restricted_document = Document.objects.create(
            client=restricted_client,
            document_type=DocumentType.WEZWANIE.value,
            file=SimpleUploadedFile("restricted.pdf", b"file"),
            awaiting_confirmation=True,
            parsed_data={"case_number": "SECRET"},
        )

        self.client.force_login(other_staff)
        response = self.client.get(
            reverse("clients:get_document_parsed_data", kwargs={"doc_id": restricted_document.pk}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["parsed_data"]["case_number"], "SECRET")

    def test_staff_role_can_start_parse_via_upload_without_feature_flag(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse(
                "clients:add_document",
                kwargs={"client_id": self.client_record.pk, "doc_type": DocumentType.WEZWANIE.value},
            ),
            data={"file": _pdf_upload("wezwanie.pdf"), "parse_wezwanie": "1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Document.objects.filter(client=self.client_record).exists())

    def test_staff_role_can_confirm_parse_without_feature_flag(self):
        document = Document.objects.create(
            client=self.client_record,
            document_type=DocumentType.WEZWANIE.value,
            file=SimpleUploadedFile("wezwanie.pdf", b"file"),
            awaiting_confirmation=True,
            parsed_data={"case_number": "WSC-II-P.123.2026"},
        )
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("clients:confirm_wezwanie_parse", kwargs={"doc_id": document.pk}),
            data={"case_number": "WSC-II-P.123.2026"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        document.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(document.awaiting_confirmation)

    def test_multiple_upload_response_contains_all_documents(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse(
                "clients:add_document",
                kwargs={"client_id": self.client_record.pk, "doc_type": DocumentType.PASSPORT.value},
            ),
            data={
                "file": [
                    _pdf_upload("passport-1.pdf", "passport one"),
                    _pdf_upload("passport-2.pdf", "passport two"),
                ],
                "expiry_date": "",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(len(payload["documents"]), 2)
        self.assertTrue(all(item["doc_id"] for item in payload["documents"]))
        self.assertEqual(
            Document.objects.filter(client=self.client_record, document_type=DocumentType.PASSPORT.value).count(),
            2,
        )

    def test_js_uses_stable_doc_id_placeholder(self):
        source = Path("static/clients/js/client/documents.js").read_text(encoding="utf-8")
        template = get_template("clients/partials/modals.html").template.source

        self.assertIn("__doc_id__", source)
        self.assertIn("__doc_id__", template)
        self.assertNotIn("parsedDataUrlTemplate.replace('0'", source)
