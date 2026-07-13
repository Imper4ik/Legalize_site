from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings

from clients.constants import DocumentType
from clients.models import Document, DocumentProcessingJob
from clients.services.cases import resolve_single_active_case
from clients.services.document_workflow import DocumentUploadResult, upload_client_document
from clients.services.wezwanie_parser import WezwanieData
from clients.testing.factories import build_pdf_upload, create_test_client, create_test_user


@override_settings(ASYNC_AUTO_OCR_PROCESSING=True)
class AsyncAutoOcrDispatchTests(TestCase):
    """Auto-recognition OCR must not run inside the upload request when
    ASYNC_AUTO_OCR_PROCESSING is on (the production default), while the
    interactive staff wezwanie parse stays synchronous."""

    def setUp(self):
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(purpose="work")
        self.case = resolve_single_active_case(self.client_obj)

    def _upload(self, doc_type: str, *, parse_requested: bool = False):
        pending = Document(file=build_pdf_upload("doc.pdf"), is_test_data=True)
        return upload_client_document(
            client=self.client_obj,
            doc_type=doc_type,
            uploaded_document=pending,
            actor=self.staff,
            parse_requested=parse_requested,
            case=self.case,
        )

    def test_auto_ocr_upload_is_queued_not_inline(self):
        with patch("clients.services.passport_parser.parse_passport_doc") as parse_mock:
            result = self._upload(DocumentType.PASSPORT.value)

        parse_mock.assert_not_called()
        self.assertTrue(result.ocr_processing_queued)
        job = DocumentProcessingJob.objects.get(document=result.document)
        self.assertEqual(job.status, DocumentProcessingJob.STATUS_PENDING)

    def test_zus_upload_is_queued_not_inline(self):
        result = self._upload(DocumentType.ZUS_RCA_OR_INSURANCE.value)
        self.assertTrue(result.ocr_processing_queued)
        self.assertTrue(
            DocumentProcessingJob.objects.filter(document=result.document).exists()
        )

    def test_interactive_wezwanie_parse_stays_inline(self):
        pending = Document(file=build_pdf_upload("wezwanie.pdf"), is_test_data=True)
        parser_calls: list[str] = []

        def fake_parser(path: str) -> WezwanieData:
            parser_calls.append(path)
            return WezwanieData()

        result = upload_client_document(
            client=self.client_obj,
            doc_type=DocumentType.WEZWANIE.value,
            uploaded_document=pending,
            actor=self.staff,
            parse_requested=True,
            case=self.case,
            parser=fake_parser,
        )

        self.assertEqual(len(parser_calls), 1, "wezwanie parse must run inline")
        self.assertFalse(result.ocr_processing_queued)

    @override_settings(ASYNC_OCR_PROCESSING=True)
    def test_global_async_override_queues_interactive_parse_too(self):
        result = self._upload(DocumentType.WEZWANIE.value, parse_requested=True)
        self.assertTrue(result.ocr_processing_queued)


@override_settings(ASYNC_AUTO_OCR_PROCESSING=False)
class InlineAutoOcrFallbackTests(TestCase):
    """With the flag off (dev/test default) auto-OCR still runs inline."""

    def setUp(self):
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(purpose="work")
        self.case = resolve_single_active_case(self.client_obj)

    def test_auto_ocr_runs_inline_when_disabled(self):
        pending = Document(file=build_pdf_upload("passport.pdf"), is_test_data=True)
        with patch(
            "clients.services.document_workflow._process_company_upload_job_inline"
        ) as inline_mock:
            inline_mock.side_effect = lambda **kwargs: DocumentUploadResult(
                document=kwargs["document"], message="inline"
            )
            result = upload_client_document(
                client=self.client_obj,
                doc_type=DocumentType.PASSPORT.value,
                uploaded_document=pending,
                actor=self.staff,
                parse_requested=False,
                case=self.case,
            )
        inline_mock.assert_called_once()
        self.assertFalse(result.ocr_processing_queued)
