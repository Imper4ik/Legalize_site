"""Case-level isolation for display number, MOS and Wniosek (spec §3, §7, §8).

A second case of the same client must never inherit the first case's number,
MOS record or confirmed Wniosek submission, and vice versa.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import translation

from clients.models import Case, MOSApplicationData
from clients.models.wniosek import WniosekAttachment, WniosekSubmission
from clients.services.cases import create_case_for_client
from clients.services.wniosek import build_submitted_document_summary
from clients.testing.factories import create_test_client, create_test_user


class DisplayNumberLegacyFallbackTests(TestCase):
    """spec §3: display_number = authority → legacy → placeholder."""

    def setUp(self) -> None:
        self.client_obj = create_test_client()
        self.case = self.client_obj.cases.get()

    def test_authority_number_wins(self) -> None:
        self.case.authority_case_number = "WSC-II-P.6151.1.2026"
        self.case.legacy_case_number = "OLD-123"
        self.assertEqual(self.case.display_number, "WSC-II-P.6151.1.2026")

    def test_legacy_number_is_fallback(self) -> None:
        self.case.authority_case_number = ""
        self.case.legacy_case_number = "OLD-123"
        self.assertEqual(self.case.display_number, "OLD-123")

    def test_placeholder_when_no_number(self) -> None:
        self.case.authority_case_number = ""
        self.case.legacy_case_number = ""
        with translation.override("ru"):
            self.assertEqual(self.case.display_number, "Дело без номера")

    def test_uuid_never_shown(self) -> None:
        self.case.authority_case_number = ""
        self.case.legacy_case_number = ""
        self.assertNotIn(str(self.case.uuid), self.case.display_number)


class MOSCaseIsolationTests(TestCase):
    """spec §8: MOS is owned by a case; two cases keep two MOS records."""

    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client()
        self.case_a = self.client_obj.cases.get()
        self.case_b = create_case_for_client(client=self.client_obj, actor=self.staff)

    def test_each_case_has_its_own_mos(self) -> None:
        # case_a already has a MOS auto-created on client creation.
        mos_a, _ = MOSApplicationData.objects.get_or_create(client=self.client_obj, case=self.case_a)
        mos_b, _ = MOSApplicationData.objects.get_or_create(client=self.client_obj, case=self.case_b)
        self.assertNotEqual(mos_a.pk, mos_b.pk)
        self.assertEqual(MOSApplicationData.objects.filter(case=self.case_a).get(), mos_a)
        self.assertEqual(MOSApplicationData.objects.filter(case=self.case_b).get(), mos_b)

    def test_one_mos_per_case_is_enforced(self) -> None:
        MOSApplicationData.objects.create(client=self.client_obj, case=self.case_b)
        # case is a OneToOneField, so a second MOS for the same case is rejected.
        with self.assertRaises(IntegrityError), transaction.atomic():
            MOSApplicationData.objects.create(client=self.client_obj, case=self.case_b)

    def test_compat_property_returns_none_for_multi_case_client(self) -> None:
        # case_a already has an auto-created MOS; add one for case_b → two total.
        MOSApplicationData.objects.create(client=self.client_obj, case=self.case_b)
        # Drop the cached_property so it recomputes against the two records.
        self.client_obj.__dict__.pop("mos_application_data", None)
        # With several MOS records the controlled accessor refuses to guess.
        self.assertIsNone(self.client_obj.mos_application_data)


class WniosekCaseIsolationTests(TestCase):
    """spec §7: a Wniosek submission in case B must not complete case A."""

    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(purpose="work")
        self.case_a = self.client_obj.cases.get()
        self.case_b = create_case_for_client(client=self.client_obj, actor=self.staff)

    def _add_submission(self, case: Case, document_type: str) -> WniosekSubmission:
        submission = WniosekSubmission.objects.create(
            client=self.client_obj,
            case=case,
            document_kind=WniosekSubmission.DocumentKind.MAZOWIECKI_APPLICATION,
            attachment_count=1,
        )
        WniosekAttachment.objects.create(
            submission=submission,
            document_type=document_type,
            entered_name="Paszport",
            position=0,
        )
        return submission

    def test_submission_in_case_b_does_not_appear_in_case_a_summary(self) -> None:
        self._add_submission(self.case_b, "passport")

        summary_a = build_submitted_document_summary(self.client_obj, case=self.case_a)
        summary_b = build_submitted_document_summary(self.client_obj, case=self.case_b)

        self.assertNotIn("passport", summary_a.get("codes", {}))
        self.assertIn("passport", summary_b.get("codes", {}))

    def test_checklist_for_case_a_ignores_case_b_submission(self) -> None:
        self._add_submission(self.case_b, "passport")

        checklist_a = self.client_obj.get_document_checklist(case=self.case_a)
        passport_rows_a = [row for row in checklist_a if row["code"] == "passport"]
        # If "passport" is a required code, it must not be marked submitted in A.
        for row in passport_rows_a:
            self.assertFalse(row["is_submitted"], row)

    def test_find_matching_attachments_scopes_to_case(self) -> None:
        from clients.constants import DocumentType
        from clients.models import Document
        from clients.services.wniosek import find_matching_attachments

        # Create verified documents for case_a and case_b
        _doc_a = Document.objects.create(
            client=self.client_obj,
            case=self.case_a,
            document_type=DocumentType.PASSPORT.value,
            file="passport_a.pdf",
            verified=True,
            is_test_data=True,
        )
        doc_b = Document.objects.create(
            client=self.client_obj,
            case=self.case_b,
            document_type=DocumentType.PASSPORT.value,
            file="passport_b.pdf",
            verified=True,
            is_test_data=True,
        )

        # Create a submission for case_b
        submission_b = self._add_submission(self.case_b, DocumentType.PASSPORT.value)

        # Match attachments for submission_b
        matches = find_matching_attachments(self.client_obj, submission_b)

        # Should only match doc_b, not doc_a!
        attachment = submission_b.attachments.get()
        self.assertEqual(matches[attachment.pk], doc_b)

        # Create a submission, then update case_id to None in the DB to simulate a legacy record
        submission_legacy = self._add_submission(self.case_a, DocumentType.PASSPORT.value)
        WniosekSubmission.objects.filter(pk=submission_legacy.pk).update(case=None)

        # Reload submission_legacy
        submission_legacy.refresh_from_db()
        self.assertIsNone(submission_legacy.case_id)

        # Match attachments for submission_legacy. Since self.client_obj has two cases,
        # get_legacy_compatibility_case will raise ValidationError, and find_matching_attachments will return no matches.
        matches_legacy = find_matching_attachments(self.client_obj, submission_legacy)
        attachment_legacy = submission_legacy.attachments.get()
        self.assertIsNone(matches_legacy[attachment_legacy.pk])
