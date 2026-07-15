from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from clients.constants import DocumentType
from clients.models import Document, DocumentProcessingJob
from clients.services.document_job_processors import _finalize_successful_ocr_job
from clients.testing.factories import create_test_client


class OcrWarningSemanticsTests(TestCase):
    def setUp(self) -> None:
        self.client_obj = create_test_client(purpose="work")
        self.document = Document.objects.create(
            client=self.client_obj,
            case=self.client_obj.cases.get(),
            document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            file=SimpleUploadedFile("zus.pdf", b"file"),
        )
        self.job = DocumentProcessingJob.objects.create(
            document=self.document,
            job_type=DocumentProcessingJob.JOB_TYPE_ZUS_OCR,
            status=DocumentProcessingJob.STATUS_PROCESSING,
        )

    def test_non_name_warning_does_not_set_name_mismatch(self) -> None:
        _finalize_successful_ocr_job(
            job_id=self.job.id,
            source_file_name=self.document.file.name,
            parsed_payload={
                "warnings": ["Could not determine the ZUS month."],
                "has_name_mismatch": False,
            },
            warnings=["Could not determine the ZUS month."],
            doc_type_display="ZUS Document",
        )

        self.document.refresh_from_db()
        self.assertFalse(self.document.ocr_name_mismatch)

    def test_actual_name_warning_sets_name_mismatch(self) -> None:
        _finalize_successful_ocr_job(
            job_id=self.job.id,
            source_file_name=self.document.file.name,
            parsed_payload={
                "warnings": ["Client name was not confirmed."],
                "has_name_mismatch": True,
            },
            warnings=["Client name was not confirmed."],
            doc_type_display="ZUS Document",
        )

        self.document.refresh_from_db()
        self.assertTrue(self.document.ocr_name_mismatch)
