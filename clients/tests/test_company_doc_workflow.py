from __future__ import annotations

from datetime import date
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from reportlab.pdfgen import canvas # type: ignore[import-untyped]

from clients.constants import DocumentType
from clients.models import Client, Document, DocumentProcessingJob
from clients.services.document_workflow import (
    upload_client_document,
)
from clients.services.company_parser import CompanyDocData


def build_pdf_upload(name: str, text: str = "NIP: 525-23-44-078") -> SimpleUploadedFile:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, text)
    pdf.save()
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/pdf")


@override_settings(ASYNC_OCR_PROCESSING=True, LANGUAGE_CODE="en")
class CompanyDocWorkflowTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(email="staff-co-workflow@example.com", password="pass", is_staff=True)
        self.client_obj = Client.objects.create(
            first_name="Jan",
            last_name="Kowalski",
            citizenship="UA",
            phone="+48777777777",
            email="jan-co-workflow@example.com",
        )

    def test_company_document_upload_queues_job(self):
        # When uploading a company doc
        doc = Document(
            client=self.client_obj,
            document_type=DocumentType.ZALACZNIK_NR_1.value,
            file=build_pdf_upload("z1.pdf"),
        )
        
        result = upload_client_document(
            client=self.client_obj,
            doc_type=DocumentType.ZALACZNIK_NR_1.value,
            uploaded_document=doc,
            actor=self.staff,
            parse_requested=True,
        )
        
        self.assertTrue(result.ocr_processing_queued)
        self.assertEqual(doc.ocr_status, "pending")
        
        # Verify job was created with correct type
        job = DocumentProcessingJob.objects.get(document=doc)
        self.assertEqual(job.job_type, DocumentProcessingJob.JOB_TYPE_COMPANY_DOC_OCR)
        self.assertEqual(job.status, DocumentProcessingJob.STATUS_PENDING)

    @patch("clients.services.document_workflow.verify_employer")
    @patch("clients.services.document_workflow.parse_company_doc")
    def test_company_document_successful_processing_with_krs(self, parse_mock, verify_mock):
        # Mock parser output for a company with valid KRS and representatives
        # Google Poland Sp. z o.o.
        parse_mock.return_value = CompanyDocData(
            text="NIP: 525-23-44-078, KRS 0000240611, salary 5000 PLN",
            nip="5252344078",
            krs="0000240611",
            salary=5000.0,
            valid_until=date(2026, 12, 31),
            detected_names=["Michal Kowalski"],
        )
        verify_mock.return_value = {
            "registry_source": "KRS",
            "company_name": "Google Poland Sp. z o.o.",
            "is_employer_active": True,
            "nip": "5252344078",
            "krs": "0000240611",
            "representatives": [],
            "signer_authorized": False,
            "matched_signer": None,
            "warnings": ["Signer not found among registry representatives."],
        }

        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZALACZNIK_NR_1.value,
            file=build_pdf_upload("z1.pdf"),
            ocr_status="pending",
        )
        DocumentProcessingJob.objects.create(
            document=doc,
            created_by=self.staff,
            status=DocumentProcessingJob.STATUS_PENDING,
            job_type=DocumentProcessingJob.JOB_TYPE_COMPANY_DOC_OCR,
        )

        # Process the job (via management command or service)
        call_command("process_document_jobs")

        doc.refresh_from_db()
        self.assertEqual(doc.ocr_status, "success")
        self.assertIsNotNone(doc.parsed_data)
        
        data = doc.parsed_data
        self.assertEqual(data["nip"], "5252344078")
        self.assertEqual(data["krs"], "0000240611")
        self.assertEqual(data["salary"], 5000.0)
        self.assertEqual(data["valid_until"], "2026-12-31")
        
        registry = data["registry_verification"]
        self.assertEqual(registry["registry_source"], "KRS")
        self.assertTrue(registry["is_employer_active"])
        # Should have warnings about signature mismatch because "Michal Kowalski" won't match Google Poland representatives
        self.assertTrue(doc.ocr_name_mismatch)
        self.assertTrue(any("Signer not found" in w for w in registry["warnings"]))

    @patch("clients.services.document_workflow.verify_employer")
    @patch("clients.services.document_workflow.parse_company_doc")
    def test_company_document_processing_low_salary_warning(self, parse_mock, verify_mock):
        # Mock parser output with salary below 4300 PLN
        parse_mock.return_value = CompanyDocData(
            text="NIP: 525-23-44-078, KRS 0000240611, salary 3200 PLN",
            nip="5252344078",
            krs="0000240611",
            salary=3200.0,
            detected_names=[],
        )
        verify_mock.return_value = {
            "registry_source": "KRS",
            "company_name": "Google Poland Sp. z o.o.",
            "is_employer_active": True,
            "nip": "5252344078",
            "krs": "0000240611",
            "representatives": [],
            "signer_authorized": True,
            "matched_signer": None,
            "warnings": [],
        }

        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZALACZNIK_NR_1.value,
            file=build_pdf_upload("z1.pdf"),
            ocr_status="pending",
        )
        DocumentProcessingJob.objects.create(
            document=doc,
            created_by=self.staff,
            status=DocumentProcessingJob.STATUS_PENDING,
            job_type=DocumentProcessingJob.JOB_TYPE_COMPANY_DOC_OCR,
        )

        call_command("process_document_jobs")

        doc.refresh_from_db()
        registry = doc.parsed_data["registry_verification"]
        
        # Verify low salary warning
        self.assertTrue(doc.ocr_name_mismatch) # Indicates warnings
        self.assertTrue(any("below the statutory minimum" in w for w in registry["warnings"]))
