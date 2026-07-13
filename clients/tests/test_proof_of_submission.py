from __future__ import annotations

import io

import segno
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from clients.constants import DocumentType
from clients.models import Document, WniosekAttachment, WniosekSubmission
from clients.services.cases import resolve_single_active_case
from clients.services.document_workflow import upload_client_document
from clients.services.proof_qr import build_proof_token, parse_proof_token
from clients.services.wniosek import build_submitted_document_summary
from clients.testing.factories import TEST_USER_CREDENTIAL, build_pdf_upload, create_test_client, create_test_user


def _qr_png_upload(submission_id: int) -> SimpleUploadedFile:
    buffer = io.BytesIO()
    segno.make(build_proof_token(submission_id), error="m").save(
        buffer, kind="png", scale=6, border=4
    )
    return SimpleUploadedFile("stamp.png", buffer.getvalue(), content_type="image/png")


class ProofOfSubmissionTests(TestCase):
    """The stamped cover sheet returned by the urząd is a generic proof of
    submission: it is exempt from document-specific OCR and closes the checklist
    positions of the submission it confirms (for any document type, not ZUS)."""

    def setUp(self):
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(purpose="work")
        self.case = resolve_single_active_case(self.client_obj)

    def _make_submission(self, *, document_type: str) -> WniosekSubmission:
        submission = WniosekSubmission.objects.create(
            client=self.client_obj,
            case=self.case,
            document_kind=WniosekSubmission.DocumentKind.MAZOWIECKI_APPLICATION,
            attachment_count=1,
            confirmed_by=self.staff,
        )
        WniosekAttachment.objects.create(
            submission=submission,
            document_type=document_type,
            entered_name="proof-covered document",
            position=0,
        )
        return submission

    def _upload_proof(self) -> Document:
        pending = Document(file=build_pdf_upload("stamp.pdf"), is_test_data=True)
        result = upload_client_document(
            client=self.client_obj,
            doc_type=DocumentType.PROOF_OF_SUBMISSION.value,
            uploaded_document=pending,
            actor=self.staff,
            parse_requested=False,
            case=self.case,
        )
        return result.document

    def test_proof_upload_skips_ocr_and_autolinks_latest_submission(self):
        submission = self._make_submission(document_type=DocumentType.PASSPORT.value)

        pending = Document(file=build_pdf_upload("stamp.pdf"), is_test_data=True)
        result = upload_client_document(
            client=self.client_obj,
            doc_type=DocumentType.PROOF_OF_SUBMISSION.value,
            uploaded_document=pending,
            actor=self.staff,
            parse_requested=False,
            case=self.case,
        )

        self.assertFalse(result.ocr_processing_queued)
        self.assertEqual(result.document.ocr_status, "skipped")
        self.assertEqual(result.document.confirms_submission_id, submission.pk)

    def test_stamp_closes_covered_position_for_any_document_type(self):
        # A passport (non-ZUS) proves the mechanism is generic, not ZUS-specific.
        submission = self._make_submission(document_type=DocumentType.PASSPORT.value)
        self._upload_proof()

        summary = build_submitted_document_summary(self.client_obj, case=self.case)
        records = summary["codes"].get(DocumentType.PASSPORT.value)
        self.assertTrue(records, "passport position should be recorded as submitted")
        self.assertTrue(records[0]["stamped"])
        self.assertIsNotNone(records[0]["stamped_at"])
        self.assertEqual(records[0]["submission_id"], submission.pk)

        checklist = self.client_obj.get_document_checklist(case=self.case)
        passport_item = next(
            item for item in checklist if item["code"] == DocumentType.PASSPORT.value
        )
        self.assertTrue(passport_item["is_submitted"])
        self.assertTrue(passport_item["is_complete"])

    def test_summary_not_stamped_without_proof(self):
        self._make_submission(document_type=DocumentType.PASSPORT.value)

        summary = build_submitted_document_summary(self.client_obj, case=self.case)
        records = summary["codes"].get(DocumentType.PASSPORT.value)
        self.assertTrue(records)
        self.assertFalse(records[0]["stamped"])
        self.assertIsNone(records[0]["stamped_at"])

    def test_cover_sheet_embeds_qr_marker_when_submission_present(self):
        submission = self._make_submission(document_type=DocumentType.PASSPORT.value)
        self.client.login(email=self.staff.email, password=TEST_USER_CREDENTIAL)

        response = self.client.get(
            reverse(
                "clients:client_document_print",
                kwargs={"pk": self.client_obj.pk, "doc_type": "mazowiecki_application"},
            ),
            {"submission_id": submission.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data:image/svg+xml")

    def test_qr_token_roundtrip_and_rejects_tampering(self):
        token = build_proof_token(7)
        self.assertEqual(parse_proof_token(token), 7)
        self.assertIsNone(parse_proof_token(None))
        self.assertIsNone(parse_proof_token("LZS1:not-a-valid-signature"))
        self.assertIsNone(parse_proof_token("plain text without prefix"))

    def test_qr_marker_links_encoded_submission_over_latest(self):
        older = self._make_submission(document_type=DocumentType.PASSPORT.value)
        newer = self._make_submission(document_type=DocumentType.HEALTH_INSURANCE.value)
        self.assertGreater(newer.pk, older.pk)  # newer is the "latest" default

        pending = Document(file=_qr_png_upload(older.pk), is_test_data=True)
        result = upload_client_document(
            client=self.client_obj,
            doc_type=DocumentType.PROOF_OF_SUBMISSION.value,
            uploaded_document=pending,
            actor=self.staff,
            parse_requested=False,
            case=self.case,
        )
        # The QR wins over the "latest submission" heuristic.
        self.assertEqual(result.document.confirms_submission_id, older.pk)

    def test_submission_stamp_properties_ignore_archived_proofs(self):
        submission = self._make_submission(document_type=DocumentType.PASSPORT.value)
        self.assertFalse(submission.has_stamped_proof)

        proof = self._upload_proof()
        submission.refresh_from_db()
        self.assertTrue(submission.has_stamped_proof)
        self.assertIsNotNone(submission.stamped_at)

        proof.archived_at = submission.confirmed_at
        proof.save(update_fields=["archived_at"])
        submission.refresh_from_db()
        self.assertFalse(submission.has_stamped_proof)
