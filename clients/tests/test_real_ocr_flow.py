from __future__ import annotations

import os
from datetime import date
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.contrib.auth import get_user_model

# Models
from clients.constants import DocumentType
from clients.models import Client, Document, DocumentProcessingJob, MOSApplicationData

# Import parsers directly to test actual file parsing
from clients.services.company_parser import parse_company_doc
from clients.services.passport_parser import parse_passport_doc
from clients.services.rental_parser import parse_rental_doc
from clients.services.zus_parser import parse_zus_doc
from clients.services.wezwanie_parser import parse_wezwanie

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
        return SimpleUploadedFile(filename, content, content_type="application/pdf")

    def test_real_company_doc_ceidg_parsing(self):
        filepath = os.path.join(self.fixtures_dir, "ceidg_real.pdf")
        parsed = parse_company_doc(filepath)
        
        self.assertIsNone(parsed.error)
        self.assertEqual(parsed.nip, "5252344078")
        self.assertIsNone(parsed.krs) # CEIDG fallback, no KRS
        self.assertEqual(parsed.salary, 5500.0)
        self.assertEqual(parsed.valid_until, date(2030, 12, 31))
        self.assertIn("Jan Kowalski", parsed.detected_names)

    def test_real_company_doc_krs_parsing(self):
        filepath = os.path.join(self.fixtures_dir, "krs_real.pdf")
        parsed = parse_company_doc(filepath)
        
        self.assertIsNone(parsed.error)
        self.assertEqual(parsed.nip, "5252344078")
        self.assertEqual(parsed.krs, "0000240611")
        self.assertIn("Jan Kowalski", parsed.detected_names)
        self.assertIn("Anna Nowak", parsed.detected_names)

    def test_real_zus_rca_parsing(self):
        filepath = os.path.join(self.fixtures_dir, "zus_rca_real.pdf")
        parsed = parse_zus_doc(filepath)
        
        self.assertEqual(parsed.employer_nip, "5252344078")
        self.assertEqual(parsed.insurance_code, "011000")
        self.assertEqual(parsed.period_month, date(2026, 4, 1))
        self.assertIn("Jan Kowalski", parsed.detected_names)

    def test_real_rental_agreement_parsing(self):
        filepath = os.path.join(self.fixtures_dir, "rental_real.pdf")
        parsed = parse_rental_doc(filepath)
        
        self.assertEqual(parsed.address, "ul. Marszalkowska 10/12, 00-590 Warszawa")
        self.assertEqual(parsed.monthly_cost, 3000.0)
        self.assertEqual(parsed.valid_until, date(2028, 1, 1))
        self.assertIn("Jan Kowalski", parsed.detected_names)
        self.assertIn("Anna Nowak", parsed.detected_names)

    def test_real_passport_parsing(self):
        filepath = os.path.join(self.fixtures_dir, "passport_real.pdf")
        parsed = parse_passport_doc(filepath)
        
        self.assertEqual(parsed.passport_number, "EE1234567")
        self.assertEqual(parsed.first_name, "Jan")
        self.assertEqual(parsed.last_name, "Kowalski")
        self.assertEqual(parsed.date_of_birth, date(1990, 5, 15))
        self.assertEqual(parsed.valid_until, date(2030, 12, 30))
        self.assertEqual(parsed.country, "POL")

    def test_real_wezwanie_parsing(self):
        filepath = os.path.join(self.fixtures_dir, "wezwanie_real.pdf")
        parsed = parse_wezwanie(filepath)
        
        self.assertEqual(parsed.case_number, "WSC-II-S.6151.97770.2026")
        self.assertEqual(parsed.fingerprints_date, date(2026, 8, 15))
        self.assertEqual(parsed.fingerprints_time, "10:30")
        self.assertEqual(parsed.wezwanie_type, "fingerprints")
        
        # Check detected documents in lowercase as parsed by the service
        self.assertIn("photos", parsed.required_documents)
        self.assertIn("passport", parsed.required_documents)
        self.assertIn("address_proof", parsed.required_documents)

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
        self.assertEqual(self.client_obj.passport_num, "EE1234567")
        self.assertFalse(doc.ocr_name_mismatch)

    def test_e2e_rental_agreement_job_processing(self):
        mos_data, _ = MOSApplicationData.objects.get_or_create(client=self.client_obj)
        mos_data.address_data = {
            "street": "Marszalkowska 10/12",
            "city": "Warszawa",
            "postal_code": "00-590",
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
        self.assertFalse(doc.ocr_name_mismatch)

    def test_e2e_company_doc_job_processing(self):
        # Create a CEIDG job
        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZALACZNIK_NR_1.value,
            file=self._get_uploaded_file("ceidg_real.pdf"),
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
        self.assertEqual(doc.parsed_data["nip"], "5252344078")
        self.assertEqual(doc.parsed_data["salary"], 5500.0)

    def test_e2e_zus_rca_job_processing(self):
        # Create a contract company doc first so we have the same NIP (5252344078)
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZALACZNIK_NR_1.value,
            ocr_status="success",
            parsed_data={"nip": "5252344078"}
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
        self.assertEqual(doc.zus_period_month, date(2026, 4, 1))
        self.assertFalse(doc.ocr_name_mismatch)
