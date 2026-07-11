from __future__ import annotations

import os
import shutil
import unittest
from datetime import date
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

# Models
from clients.constants import DocumentType
from clients.models import Client, Document, DocumentProcessingJob, MOSApplicationData

# Import parsers directly to test actual file parsing
from clients.services.company_parser import parse_company_doc
from clients.services.passport_parser import parse_passport_doc
from clients.services.rental_parser import parse_rental_doc
from clients.services.wezwanie_parser import parse_wezwanie
from clients.services.zus_parser import parse_zus_doc

# Both binaries are required for the real OCR flow. pytest honours the marker
# below, but Django's own test runner (manage.py test) ignores pytest markers,
# so a unittest-level skip is needed for the suite to skip — not fail — when the
# binaries are absent (e.g. a dev box without Tesseract/Poppler installed).
_OCR_BINARIES_AVAILABLE = shutil.which("tesseract") is not None and shutil.which("pdftoppm") is not None


@pytest.mark.skipif(
    not _OCR_BINARIES_AVAILABLE,
    reason="Real OCR flow requires the Tesseract and Poppler binaries.",
)
@unittest.skipUnless(
    _OCR_BINARIES_AVAILABLE,
    "Real OCR flow requires the Tesseract and Poppler binaries.",
)
@override_settings(ASYNC_OCR_PROCESSING=True)
class RealOCRFlowTests(TestCase):
    def setUp(self):
        self.fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            email="real-ocr-flow-staff@example.com",
            password="pass",
            is_staff=True
        )
        self.client_obj = Client.objects.create(
            first_name="Jan",
            last_name="Kowalski",
            birth_date=date(1990, 5, 15),
            citizenship="PL",
            phone="+48777777777",
            email="jan-kowalski-real-ocr@example.com",
            passport_num="",
        )

    def _get_uploaded_file(self, filename: str) -> SimpleUploadedFile:
        filepath = os.path.join(self.fixtures_dir, filename)
        with open(filepath, "rb") as f:
            content = f.read()
        return SimpleUploadedFile(filename, content, content_type="application/pdf" if filename.endswith(".pdf") else "image/png")

    # --- Digital PDF Parsing Tests (pypdf engine) ---

    def test_real_company_doc_ceidg_parsing(self):
        filepath = os.path.join(self.fixtures_dir, "ceidg_real.pdf")
        parsed = parse_company_doc(filepath)

        self.assertIsNone(parsed.error)
        self.assertIsNone(parsed.nip)
        self.assertIsNone(parsed.krs)
        self.assertIsNone(parsed.salary)
        self.assertIsNone(parsed.valid_until)

    def test_real_company_doc_krs_parsing(self):
        filepath = os.path.join(self.fixtures_dir, "krs_real.pdf")
        parsed = parse_company_doc(filepath)

        self.assertIsNone(parsed.error)
        self.assertEqual(parsed.nip, "5260250481")
        self.assertEqual(parsed.krs, "0000225587")

    def test_real_zus_rca_parsing(self):
        filepath = os.path.join(self.fixtures_dir, "zus_rca_real.pdf")
        parsed = parse_zus_doc(filepath)

        self.assertIsNone(parsed.error)
        self.assertIsNone(parsed.employer_nip)
        self.assertIsNone(parsed.insurance_code)
        self.assertIsNone(parsed.period_month)
        self.assertEqual(parsed.zus_form_type, "RCA")

    def test_real_rental_agreement_parsing(self):
        filepath = os.path.join(self.fixtures_dir, "rental_real.pdf")
        parsed = parse_rental_doc(filepath)

        self.assertIsNone(parsed.error)
        self.assertIn("Przeskok 2", parsed.address)
        self.assertIsNone(parsed.monthly_cost)
        self.assertIsNone(parsed.valid_until)

    def test_real_passport_parsing(self):
        filepath = os.path.join(self.fixtures_dir, "passport_real.pdf")
        parsed = parse_passport_doc(filepath)

        self.assertIsNone(parsed.error)
        self.assertIsNone(parsed.passport_number)
        self.assertEqual(parsed.first_name, "Republic")
        self.assertEqual(parsed.last_name, "Of")

    def test_real_wezwanie_parsing(self):
        filepath = os.path.join(self.fixtures_dir, "wezwanie_real.pdf")
        parsed = parse_wezwanie(filepath)

        self.assertEqual(parsed.case_number, "WSC-II-S.6151.97770.2026")
        self.assertEqual(parsed.fingerprints_date, date(2026, 8, 15))
        self.assertEqual(parsed.fingerprints_time, "10:30")
        self.assertEqual(parsed.wezwanie_type, "fingerprints")
        self.assertIn("address_proof", parsed.required_documents)
        self.assertIn("passport", parsed.required_documents)
        self.assertIn("photos", parsed.required_documents)

    # --- Raster Image (PNG/Scan) OCR Parsing Tests ---

    def test_raster_image_passport_ocr(self):
        filepath = os.path.join(self.fixtures_dir, "passport_scan_specimen.png")
        parsed = parse_passport_doc(filepath)

        self.assertIsNone(parsed.error)
        self.assertIsNotNone(parsed.text)
        self.assertTrue(len(parsed.text) > 100)

    # --- End-To-End Job Integration Tests ---

    def test_e2e_passport_job_processing(self):
        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file=self._get_uploaded_file("passport_real.pdf"),
            ocr_status="pending",
        )
        DocumentProcessingJob.objects.create(
            document=doc,
            created_by=self.staff,
            status=DocumentProcessingJob.STATUS_PENDING,
            job_type=DocumentProcessingJob.JOB_TYPE_PASSPORT_OCR,
        )

        call_command("process_document_jobs")

        doc.refresh_from_db()
        self.client_obj.refresh_from_db()

        self.assertEqual(doc.ocr_status, "success")
        self.assertEqual(self.client_obj.passport_num, "")
        self.assertTrue(doc.ocr_name_mismatch)

    def test_e2e_rental_agreement_job_processing(self):
        mos_data, _ = MOSApplicationData.objects.get_or_create(client=self.client_obj)
        mos_data.address_data = {
            "street": "Przeskok 2",
            "city": "Warszawa",
            "postal_code": "00-032",
        }
        mos_data.save()

        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ADDRESS_PROOF.value,
            file=self._get_uploaded_file("rental_real.pdf"),
            ocr_status="pending",
        )
        DocumentProcessingJob.objects.create(
            document=doc,
            created_by=self.staff,
            status=DocumentProcessingJob.STATUS_PENDING,
            job_type=DocumentProcessingJob.JOB_TYPE_RENTAL_OCR,
        )

        call_command("process_document_jobs")

        doc.refresh_from_db()
        self.assertEqual(doc.ocr_status, "success")
        self.assertTrue(doc.ocr_name_mismatch)

    @patch("clients.services.document_workflow.verify_employer")
    def test_e2e_company_doc_job_processing(self, verify_employer_mock):
        verify_employer_mock.return_value = {
            "registry_source": "KRS",
            "company_name": "TEST COMPANY",
            "is_employer_active": True,
            "nip": "5260250481",
            "krs": "0000225587",
            "representatives": [],
            "signer_authorized": False,
            "matched_signer": None,
            "warnings": [],
        }
        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZALACZNIK_NR_1.value,
            file=self._get_uploaded_file("krs_real.pdf"),
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
        self.assertEqual(doc.ocr_status, "success")
        self.assertEqual(doc.parsed_data["nip"], "5260250481")
        self.assertEqual(doc.parsed_data["krs"], "0000225587")

    def test_e2e_zus_rca_job_processing(self):
        # Create a contract company doc first so we have the same NIP
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZALACZNIK_NR_1.value,
            ocr_status="success",
            parsed_data={"nip": "5260250481"}
        )

        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            file=self._get_uploaded_file("zus_rca_real.pdf"),
            ocr_status="pending",
        )
        DocumentProcessingJob.objects.create(
            document=doc,
            created_by=self.staff,
            status=DocumentProcessingJob.STATUS_PENDING,
            job_type=DocumentProcessingJob.JOB_TYPE_ZUS_OCR,
        )

        call_command("process_document_jobs")

        doc.refresh_from_db()
        self.assertEqual(doc.ocr_status, "success")
        self.assertIsNone(doc.zus_period_month)
        self.assertTrue(doc.ocr_name_mismatch)
