"""The case document checklist must visually distinguish a document that needs
an OCR-data confirmation from one that just needs a manual verification, so
staff can tell at a glance which is which (collapsed-row badges).
"""
from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from clients.constants import DocumentType
from clients.testing.factories import (
    TEST_USER_CREDENTIAL,
    create_test_client,
    create_test_document,
    create_test_user,
)


class ChecklistReviewBadgeTests(TestCase):
    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(purpose="work")
        self.case = self.client_obj.cases.get()

        # One document with OCR-recognised data awaiting confirmation.
        self.ocr_doc = create_test_document(
            self.client_obj, case=self.case, doc_type=DocumentType.PASSPORT.value
        )
        self.ocr_doc.awaiting_confirmation = True
        self.ocr_doc.verified = False
        self.ocr_doc.save(update_fields=["awaiting_confirmation", "verified"])

        # One document that only needs a plain manual verification.
        self.review_doc = create_test_document(
            self.client_obj, case=self.case, doc_type="oryginaly_umow_o_prace"
        )
        self.review_doc.awaiting_confirmation = False
        self.review_doc.verified = False
        self.review_doc.save(update_fields=["awaiting_confirmation", "verified"])

    def test_checklist_flags_separate_ocr_from_verification(self) -> None:
        rows = {r["code"]: r for r in self.client_obj.get_document_checklist(case=self.case)}
        passport = rows[DocumentType.PASSPORT.value]
        umowa = rows["oryginaly_umow_o_prace"]

        self.assertTrue(passport["has_ocr_review"])
        self.assertFalse(passport["needs_verification"])

        self.assertFalse(umowa["has_ocr_review"])
        self.assertTrue(umowa["needs_verification"])

    def test_checklist_rows_expose_the_problem_document_ids(self) -> None:
        rows = {r["code"]: r for r in self.client_obj.get_document_checklist(case=self.case)}
        self.assertEqual(rows["passport"]["ocr_review_doc_id"], self.ocr_doc.id)
        self.assertEqual(rows["oryginaly_umow_o_prace"]["verification_doc_id"], self.review_doc.id)

    def test_case_detail_renders_both_badges(self) -> None:
        from django.utils import translation

        self.client.login(email=self.staff.email, password=TEST_USER_CREDENTIAL)
        # Request the Russian locale explicitly: the badge labels are now
        # translated, so the default (Polish) page no longer contains the
        # Russian source strings.
        with translation.override("ru"):
            resp = self.client.get(reverse("clients:case_detail", kwargs={"pk": self.case.pk}))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("OCR-проверка", body)
        self.assertIn("Ждёт проверки", body)
        # The badges are clickable and point at the exact problem document.
        self.assertIn('data-jump-doc="%d" data-jump-action="ocr"' % self.ocr_doc.id, body)
        self.assertIn('data-jump-doc="%d" data-jump-action="verify"' % self.review_doc.id, body)
        self.assertIn('id="doc-row-%d"' % self.ocr_doc.id, body)
