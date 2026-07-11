from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from clients.constants import DocumentType
from clients.models import Client, Document, DocumentProcessingJob, MOSApplicationData
from clients.services.document_workflow import upload_client_document
from clients.services.insurance_parser import InsuranceDocData

# Import parsers directly to test parser logic
from clients.services.passport_parser import PassportDocData
from clients.services.rental_parser import RentalDocData
from clients.services.zus_parser import ZusDocData, parse_zus_doc
from clients.tests.test_company_doc_workflow import build_pdf_upload


@override_settings(ASYNC_OCR_PROCESSING=True, LANGUAGE_CODE="en")
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

        self.assertEqual(doc.ocr_status, "success")
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
        self.assertEqual(doc.ocr_status, "success")
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
        self.assertEqual(doc.ocr_status, "success")
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

    def test_zus_parser_extracts_contextual_insurance_code(self):
        text = "ZUS ZUA\nKod tytu\u0142u ubezpieczenia: 04 11 00\nUbezpieczony: Jan Kowalski"

        with patch("clients.services.zus_parser.extract_text", return_value=text):
            parsed = parse_zus_doc("fake-zus.pdf")

        self.assertEqual(parsed.insurance_code, "041100")

    def test_zus_parser_does_not_use_identifier_as_insurance_code(self):
        text = "03. TYP 04. IDENTYFIKATOR\nDARYA P 043208 11580"

        with patch("clients.services.zus_parser.extract_text", return_value=text):
            parsed = parse_zus_doc("fake-zus.pdf")

        self.assertIsNone(parsed.insurance_code)

    def test_zus_parser_extracts_period_from_real_rca_layout(self):
        # Real ZUS RCA bank prints the period in the "Identyfikator raportu"
        # field as "nr miesiac rok" (e.g. 01 05 2026), space-separated and
        # without a "za miesiac" keyword.
        text = (
            "ZUS RCA\nImienny raport miesieczny o naleznych skladkach\n"
            "III. Identyfikator raportu\n01 05 2026\nPlatnik: FIRMA"
        )
        with patch("clients.services.zus_parser.extract_text", return_value=text):
            parsed = parse_zus_doc("fake-zus.pdf")
        self.assertEqual(parsed.period_month, date(2026, 5, 1))

    def test_zus_parser_extracts_period_from_labelled_month_year(self):
        text = "ZUS RCA imienny raport miesieczny\nMiesiac 05 Rok 2026\nJan Kowalski"
        with patch("clients.services.zus_parser.extract_text", return_value=text):
            parsed = parse_zus_doc("fake-zus.pdf")
        self.assertEqual(parsed.period_month, date(2026, 5, 1))

    def test_zus_parser_ignores_print_date_as_period(self):
        # A full print/upload date must not be mistaken for the reporting period.
        text = "ZUS RCA\nData druku 25.05.2026\nJan Kowalski"
        with patch("clients.services.zus_parser.extract_text", return_value=text):
            parsed = parse_zus_doc("fake-zus.pdf")
        self.assertIsNone(parsed.period_month)

    @patch("clients.services.zus_parser.parse_zus_doc")
    def test_zus_document_processing(self, parse_mock):
        # Upload a completed company doc first to have NIP in database
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZALACZNIK_NR_1.value,
            ocr_status="success",
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
        self.assertEqual(doc.ocr_status, "success")
        self.assertFalse(doc.ocr_name_mismatch) # Name, NIP match contract, code is standard 011000!

    @patch("clients.services.zus_parser.parse_zus_doc")
    def test_zus_document_warnings(self, parse_mock):
        # Mismatch NIP and wrong insurance code
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZALACZNIK_NR_1.value,
            ocr_status="success",
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

    @patch("clients.services.zus_parser.parse_zus_doc")
    def test_zus_period_month_saved_and_exposed_in_parsed_data(self, parse_mock):
        case = self.client_obj.cases.get()
        case.workflow_stage = "waiting_decision"
        case.save(update_fields=["workflow_stage"])
        parse_mock.return_value = ZusDocData(
            text="ZUS RCA",
            employer_nip="525-23-44-078",
            insurance_code="011000",
            detected_names=["Jan Kowalski"],
            period_month=date(2026, 4, 1),
        )
        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            file=build_pdf_upload("zus_period.pdf"),
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
        self.assertEqual(doc.parsed_data.get("period_month"), "2026-04-01")

    @patch("clients.services.zus_parser.parse_zus_doc")
    def test_duplicate_zus_period_does_not_fail_job(self, parse_mock):
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            file=build_pdf_upload("zus_existing.pdf"),
            zus_period_month=date(2026, 4, 1),
            ocr_status="success",
        )
        parse_mock.return_value = ZusDocData(
            text="ZUS RCA",
            employer_nip="525-23-44-078",
            insurance_code="011000",
            detected_names=["Jan Kowalski"],
            period_month=date(2026, 4, 1),
        )
        second = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            file=build_pdf_upload("zus_second.pdf"),
            ocr_status="pending",
        )
        DocumentProcessingJob.objects.create(
            document=second,
            created_by=self.staff,
            status=DocumentProcessingJob.STATUS_PENDING,
            job_type=DocumentProcessingJob.JOB_TYPE_ZUS_OCR,
        )
        call_command("process_document_jobs")
        second.refresh_from_db()
        self.assertEqual(second.ocr_status, "success")
        self.assertIsNone(second.zus_period_month)
        self.assertEqual(second.parsed_data.get("period_month"), "2026-04-01")
        self.assertTrue(any("already" in w or "exists" in w or "уже" in w or "существует" in w for w in second.parsed_data.get("warnings", [])))

    def test_zus_rca_or_insurance_job_type_by_month_field(self):
        doc_with_month = Document(file=build_pdf_upload("with_month.pdf"), zus_period_month=date(2026, 4, 1))
        res = upload_client_document(
            client=self.client_obj,
            doc_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            uploaded_document=doc_with_month,
            actor=self.staff,
            parse_requested=False,
        )
        job_with_month = DocumentProcessingJob.objects.get(document=res.document)
        self.assertEqual(job_with_month.job_type, DocumentProcessingJob.JOB_TYPE_ZUS_OCR)

        doc_without_month = Document(file=build_pdf_upload("without_month.pdf"))
        res2 = upload_client_document(
            client=self.client_obj,
            doc_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            uploaded_document=doc_without_month,
            actor=self.staff,
            parse_requested=False,
        )
        job_without_month = DocumentProcessingJob.objects.get(document=res2.document)
        self.assertEqual(job_without_month.job_type, DocumentProcessingJob.JOB_TYPE_INSURANCE_OCR)

    def test_job_type_for_health_insurance_and_zus_history(self):
        health_doc = Document(file=build_pdf_upload("health.pdf"))
        health_res = upload_client_document(
            client=self.client_obj,
            doc_type=DocumentType.HEALTH_INSURANCE.value,
            uploaded_document=health_doc,
            actor=self.staff,
            parse_requested=False,
        )
        health_job = DocumentProcessingJob.objects.get(document=health_res.document)
        self.assertEqual(health_job.job_type, DocumentProcessingJob.JOB_TYPE_INSURANCE_OCR)

        zus_hist = Document(file=build_pdf_upload("zus_hist.pdf"))
        zus_res = upload_client_document(
            client=self.client_obj,
            doc_type=DocumentType.ZUS_CONTRIBUTION_HISTORY.value,
            uploaded_document=zus_hist,
            actor=self.staff,
            parse_requested=False,
        )
        zus_job = DocumentProcessingJob.objects.get(document=zus_res.document)
        self.assertEqual(zus_job.job_type, DocumentProcessingJob.JOB_TYPE_ZUS_OCR)

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
        self.assertEqual(doc.ocr_status, "success")
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
        self.assertEqual(doc.ocr_status, "success")
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

    @patch("clients.services.zus_parser.parse_zus_doc")
    @patch("clients.services.insurance_parser.parse_insurance_doc")
    def test_zus_rca_without_month_is_not_treated_as_insurance(self, insurance_mock, zus_mock):
        """A ZUS RCA uploaded to the combined slot without a manually selected month
        is routed to the insurance parser, but must be re-detected as a ZUS form
        and processed by the ZUS parser instead of producing insurance warnings."""
        insurance_mock.return_value = InsuranceDocData(
            text=(
                "ZUS RCA\nImienny raport miesieczny o naleznych skladkach\n"
                "Jan Kowalski\nKod tytulu ubezpieczenia: 01 10 00\nZa miesiac 05.2026"
            ),
            valid_until=None,
            coverage_amount=None,
            currency=None,
            detected_names=["Jan Kowalski"],
        )
        zus_mock.return_value = ZusDocData(
            text="ZUS RCA Imienny raport miesieczny",
            employer_nip=None,
            insurance_code="011000",
            period_month=date(2026, 5, 1),
            detected_names=["Jan Kowalski"],
            zus_form_type="RCA",
        )

        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            file=build_pdf_upload("zus_rca_no_month.pdf"),
            ocr_status="pending",
            zus_period_month=None,
        )
        DocumentProcessingJob.objects.create(
            document=doc,
            created_by=self.staff,
            status=DocumentProcessingJob.STATUS_PENDING,
            job_type=DocumentProcessingJob.JOB_TYPE_INSURANCE_OCR,
        )

        call_command("process_document_jobs")

        doc.refresh_from_db()
        # ZUS parser handled it: form type recorded, no bogus insurance warnings.
        self.assertEqual(doc.parsed_data.get("zus_form_type"), "RCA")
        zus_mock.assert_called_once()
        warnings = doc.parsed_data.get("warnings", [])
        self.assertFalse(any("insurance coverage" in w.lower() for w in warnings))
        self.assertFalse(any("insurance expiration" in w.lower() for w in warnings))
