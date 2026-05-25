from __future__ import annotations

import re
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from clients.constants import DocumentType
from clients.models import Client, Document, DocumentProcessingJob, MOSApplicationData
from clients.tests.test_company_doc_workflow import build_pdf_upload

# Import parsers directly to test parser logic
from clients.services.passport_parser import PassportDocData
from clients.services.rental_parser import RentalDocData
from clients.services.zus_parser import ZusDocData
from clients.services.insurance_parser import InsuranceDocData


@override_settings(ASYNC_OCR_PROCESSING=True)
class NewOcrWorkflowsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(email="staff-ocr-workflow@example.com", password="pass", is_staff=True)
        self.client_obj = Client.objects.create(
            first_name="Jan",
            last_name="Kowalski",
            birth_date=date(1990, 5, 15),
            citizenship="UA",
            phone="+48777777777",
            email="jan-ocr-workflow@example.com",
            passport_num="", # empty, so OCR should update it
        )

    @patch("clients.services.passport_parser.parse_passport_doc")
    def test_passport_successful_processing_and_autoupdate(self, parse_mock):
        # 1. Mock passport parser output
        parse_mock.return_value = PassportDocData(
            text="PASSPORT REPUBLIC OF POLAND\nName: JAN KOWALSKI\nDOB: 15.05.1990\nExpiry: 30.12.2030\nNo: EE1234567",
            passport_number="EE1234567",
            first_name="Jan",
            last_name="Kowalski",
            date_of_birth=date(1990, 5, 15),
            valid_until=date(2030, 12, 30),
            country="POL",
        )

        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file=build_pdf_upload("passport.pdf"),
            ocr_status="pending",
        )
        DocumentProcessingJob.objects.create(
            document=doc,
            created_by=self.staff,
            status=DocumentProcessingJob.STATUS_PENDING,
            job_type=DocumentProcessingJob.JOB_TYPE_PASSPORT_OCR,
        )

        call_command("process_document_jobs")

        # Refresh
        doc.refresh_from_db()
        self.client_obj.refresh_from_db()

        self.assertEqual(doc.ocr_status, "completed")
        self.assertFalse(doc.ocr_name_mismatch) # No warnings
        
        # Verify autoupdate of passport_num
        self.assertEqual(self.client_obj.passport_num, "EE1234567")
        self.assertIn("Updated missing client passport number", doc.parsed_data["auto_updates"][0])

    @patch("clients.services.passport_parser.parse_passport_doc")
    def test_passport_warnings_mismatch(self, parse_mock):
        # Name and DOB mismatch, and expired
        parse_mock.return_value = PassportDocData(
            text="PASSPORT\nName: JOHN SMITH\nDOB: 01.01.1980\nExpiry: 01.01.2020\nNo: XX9876543",
            passport_number="XX9876543",
            first_name="John",
            last_name="Smith",
            date_of_birth=date(1980, 1, 1),
            valid_until=date(2020, 1, 1),
            country="USA",
        )

        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file=build_pdf_upload("passport_mismatch.pdf"),
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
        self.assertEqual(doc.ocr_status, "completed")
        self.assertTrue(doc.ocr_name_mismatch) # Yes, warnings
        
        warnings = doc.parsed_data["warnings"]
        self.assertTrue(any("Client name not matched" in w for w in warnings))
        self.assertTrue(any("Date of Birth" in w for w in warnings))
        self.assertTrue(any("has expired" in w for w in warnings))

    @patch("clients.services.rental_parser.parse_rental_doc")
    def test_rental_agreement_processing(self, parse_mock):
        # Create/Get MOSApplicationData to mock onboarding address
        mos_data, _ = MOSApplicationData.objects.get_or_create(client=self.client_obj)
        mos_data.address_data = {
            "street": "Marszałkowska 10/12",
            "city": "Warszawa",
            "postal_code": "00-590",
        }
        mos_data.save()

        parse_mock.return_value = RentalDocData(
            text="UMOWA NAJMU LOKALU\nWynajmujacy: Jan Kowalski\nAdres: ul. Marszałkowska 10/12, 00-590 Warszawa\nCzynsz: 3000 PLN\nValid until: 01.01.2028",
            address="ul. Marszałkowska 10/12, 00-590 Warszawa",
            valid_until=date(2028, 1, 1),
            monthly_cost=3000.0,
            detected_names=["Jan Kowalski"],
        )

        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ADDRESS_PROOF.value,
            file=build_pdf_upload("rental.pdf"),
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
        self.assertEqual(doc.ocr_status, "completed")
        self.assertFalse(doc.ocr_name_mismatch) # No warnings, address and name match!

    @patch("clients.services.rental_parser.parse_rental_doc")
    def test_rental_agreement_mismatches(self, parse_mock):
        # Different address and expired
        mos_data, _ = MOSApplicationData.objects.get_or_create(client=self.client_obj)
        mos_data.address_data = {
            "street": "Marszałkowska 10/12",
            "city": "Warszawa",
            "postal_code": "00-590",
        }
        mos_data.save()

        parse_mock.return_value = RentalDocData(
            text="UMOWA NAJMU LOKALU\nWynajmujacy: John Smith\nAdres: ul. Piotrkowska 99, 90-004 Lodz\nCzynsz: 1500 PLN\nValid until: 01.01.2020",
            address="ul. Piotrkowska 99, 90-004 Lodz",
            valid_until=date(2020, 1, 1),
            monthly_cost=1500.0,
            detected_names=["John Smith"],
        )

        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ADDRESS_PROOF.value,
            file=build_pdf_upload("rental_bad.pdf"),
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
        self.assertTrue(doc.ocr_name_mismatch)
        warnings = doc.parsed_data["warnings"]
        self.assertTrue(any("Client name not matched" in w for w in warnings))
        self.assertTrue(any("address does not match" in w for w in warnings))
        self.assertTrue(any("expired on" in w for w in warnings))

    @patch("clients.services.zus_parser.parse_zus_doc")
    def test_zus_document_processing(self, parse_mock):
        # Upload a completed company doc first to have NIP in database
        company_doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZALACZNIK_NR_1.value,
            ocr_status="completed",
            parsed_data={"nip": "5252344078"}
        )

        parse_mock.return_value = ZusDocData(
            text="ZUS ZUA DEKLARACJA\nUbezpieczony: Jan Kowalski\nPlatnik NIP: 525-23-44-078\nKod tytulu ubezpieczenia: 011000",
            employer_nip="525-23-44-078",
            insurance_code="011000",
            detected_names=["Jan Kowalski"],
        )

        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            file=build_pdf_upload("zus.pdf"),
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
        self.assertEqual(doc.ocr_status, "completed")
        self.assertFalse(doc.ocr_name_mismatch) # Name, NIP match contract, code is standard 011000!

    @patch("clients.services.zus_parser.parse_zus_doc")
    def test_zus_document_warnings(self, parse_mock):
        # Mismatch NIP and wrong insurance code
        company_doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZALACZNIK_NR_1.value,
            ocr_status="completed",
            parsed_data={"nip": "5252344078"}
        )

        parse_mock.return_value = ZusDocData(
            text="ZUS ZUA DEKLARACJA\nUbezpieczony: Jan Kowalski\nPlatnik NIP: 999-99-99-999\nKod tytulu ubezpieczenia: 051000",
            employer_nip="999-99-99-999",
            insurance_code="051000",
            detected_names=["Jan Kowalski"],
        )

        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            file=build_pdf_upload("zus_bad.pdf"),
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
        self.assertTrue(doc.ocr_name_mismatch)
        warnings = doc.parsed_data["warnings"]
        self.assertTrue(any("does not match contract NIP" in w for w in warnings))
        self.assertTrue(any("non-standard employment type" in w for w in warnings))

    @patch("clients.services.insurance_parser.parse_insurance_doc")
    def test_insurance_policy_processing(self, parse_mock):
        # EUR coverage >= 30000
        parse_mock.return_value = InsuranceDocData(
            text="POLISA UBEZPIECZENIOWA\nInsured: Jan Kowalski\nLimit: 30000 EUR\nExpiry: 01.01.2028",
            valid_until=date(2028, 1, 1),
            coverage_amount=30000.0,
            currency="EUR",
            detected_names=["Jan Kowalski"],
        )

        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.HEALTH_INSURANCE.value,
            file=build_pdf_upload("insurance_eur.pdf"),
            ocr_status="pending",
        )
        DocumentProcessingJob.objects.create(
            document=doc,
            created_by=self.staff,
            status=DocumentProcessingJob.STATUS_PENDING,
            job_type=DocumentProcessingJob.JOB_TYPE_INSURANCE_OCR,
        )

        call_command("process_document_jobs")

        doc.refresh_from_db()
        self.assertEqual(doc.ocr_status, "completed")
        self.assertFalse(doc.ocr_name_mismatch)

    @patch("clients.services.insurance_parser.parse_insurance_doc")
    def test_insurance_policy_pln_processing(self, parse_mock):
        # PLN coverage >= 120000
        parse_mock.return_value = InsuranceDocData(
            text="POLISA UBEZPIECZENIOWA\nInsured: Jan Kowalski\nSuma: 120 000 PLN\nExpiry: 01.01.2028",
            valid_until=date(2028, 1, 1),
            coverage_amount=120000.0,
            currency="PLN",
            detected_names=["Jan Kowalski"],
        )

        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.HEALTH_INSURANCE.value,
            file=build_pdf_upload("insurance_pln.pdf"),
            ocr_status="pending",
        )
        DocumentProcessingJob.objects.create(
            document=doc,
            created_by=self.staff,
            status=DocumentProcessingJob.STATUS_PENDING,
            job_type=DocumentProcessingJob.JOB_TYPE_INSURANCE_OCR,
        )

        call_command("process_document_jobs")

        doc.refresh_from_db()
        self.assertEqual(doc.ocr_status, "completed")
        self.assertFalse(doc.ocr_name_mismatch)

    @patch("clients.services.insurance_parser.parse_insurance_doc")
    def test_insurance_policy_warnings(self, parse_mock):
        # Insufficient coverage and expired
        parse_mock.return_value = InsuranceDocData(
            text="POLISA UBEZPIECZENIOWA\nInsured: John Smith\nSuma: 10000 EUR\nExpiry: 01.01.2020",
            valid_until=date(2020, 1, 1),
            coverage_amount=10000.0,
            currency="EUR",
            detected_names=["John Smith"],
        )

        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.HEALTH_INSURANCE.value,
            file=build_pdf_upload("insurance_bad.pdf"),
            ocr_status="pending",
        )
        DocumentProcessingJob.objects.create(
            document=doc,
            created_by=self.staff,
            status=DocumentProcessingJob.STATUS_PENDING,
            job_type=DocumentProcessingJob.JOB_TYPE_INSURANCE_OCR,
        )

        call_command("process_document_jobs")

        doc.refresh_from_db()
        self.assertTrue(doc.ocr_name_mismatch)
        warnings = doc.parsed_data["warnings"]
        self.assertTrue(any("Client name not matched" in w for w in warnings))
        self.assertTrue(any("below the statutory minimum" in w for w in warnings))
        self.assertTrue(any("expired on" in w for w in warnings))
