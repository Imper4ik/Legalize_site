"""A document uploaded to one case must not leak into another case.

For a client with two active cases (work + study), uploading a ZUS RCA document
to the work case must not change the study case's checklist, and must not create
tasks or reminders scoped to the study case.
"""
from __future__ import annotations

from datetime import date

from django.test import TestCase, override_settings

from clients.constants import DocumentType
from clients.models import Case, MOSApplicationData, Reminder, StaffTask
from clients.services.document_workflow import upload_client_document
from clients.testing.factories import create_test_client, create_test_document, create_test_user

ZUS = DocumentType.ZUS_RCA_OR_INSURANCE.value


class CaseIsolationDocumentTests(TestCase):
    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(purpose="work")
        self.work_case = self.client_obj.cases.get()
        self.work_case.application_purpose = "work"
        self.work_case.workflow_stage = "document_collection"
        self.work_case.save(update_fields=["application_purpose", "workflow_stage"])
        self.study_case = Case.objects.create(
            client=self.client_obj,
            application_purpose="study",
            workflow_stage="document_collection",
            status="active",
        )

    def _codes(self, case: Case) -> dict:
        return {row["code"]: row for row in self.client_obj.get_document_checklist(case=case)}

    def test_upload_to_work_case_does_not_touch_study_checklist(self) -> None:
        create_test_document(
            self.client_obj,
            case=self.work_case,
            doc_type=ZUS,
            verified=True,
            zus_period_month=date(2026, 4, 1),
        )

        work_rows = self._codes(self.work_case)
        study_rows = self._codes(self.study_case)

        # The work case sees the uploaded ZUS document...
        self.assertIn(ZUS, work_rows)
        self.assertTrue(work_rows[ZUS]["is_uploaded"])
        # ...the study case does not (row absent or simply not uploaded).
        self.assertFalse(study_rows.get(ZUS, {}).get("is_uploaded", False))
        # And the study case owns no documents at all.
        self.assertEqual(self.study_case.documents.count(), 0)

    @override_settings(ASYNC_OCR_PROCESSING=True)
    def test_upload_scopes_document_and_side_effects_to_its_case(self) -> None:
        study_tasks_before = StaffTask.objects.filter(case=self.study_case).count()
        study_reminders_before = Reminder.objects.filter(case=self.study_case).count()

        uploaded = create_test_document(
            self.client_obj, case=self.work_case, doc_type=ZUS, zus_period_month=date(2026, 5, 1)
        )
        # Persist through the real workflow so tasks/OCR jobs are created.
        result = upload_client_document(
            client=self.client_obj,
            doc_type=ZUS,
            uploaded_document=uploaded,
            actor=None,  # non-staff -> raises a document_review task
            case=self.work_case,
            parse_requested=False,
        )

        # The document and its processing job belong to the work case.
        self.assertEqual(result.document.case_id, self.work_case.id)
        # No task or reminder was attached to the study case.
        self.assertEqual(StaffTask.objects.filter(case=self.study_case).count(), study_tasks_before)
        self.assertEqual(Reminder.objects.filter(case=self.study_case).count(), study_reminders_before)
        # Any created task is scoped to the work case.
        self.assertFalse(StaffTask.objects.filter(case=self.study_case).exists())


class LegalStayReminderCaseScopingTests(TestCase):
    def setUp(self) -> None:
        self.client_obj = create_test_client(purpose="work")
        self.work_case = self.client_obj.cases.get()
        self.study_case = Case.objects.create(
            client=self.client_obj,
            application_purpose="study",
            workflow_stage="document_collection",
            status="active",
        )
        self.work_mos, _ = MOSApplicationData.objects.get_or_create(
            client=self.client_obj, case=self.work_case
        )
        self.work_mos.legal_stay_until = date(2026, 7, 31)
        self.work_mos.save(update_fields=["legal_stay_until"])
        self.study_mos, _ = MOSApplicationData.objects.get_or_create(
            client=self.client_obj, case=self.study_case
        )
        self.study_mos.legal_stay_until = date(2027, 1, 15)
        self.study_mos.save(update_fields=["legal_stay_until"])

    def _legal_stay_reminder(self, case: Case) -> Reminder:
        return Reminder.objects.create(
            client=self.client_obj,
            case=case,
            reminder_type="legal_stay",
            due_date=date(2026, 7, 30),
            title="Legal stay filing deadline",
        )

    def test_note_uses_own_case_mos_not_arbitrary(self) -> None:
        reminder = self._legal_stay_reminder(self.work_case)
        notes = reminder.display_notes
        self.assertIn("31.07.2026", notes)      # work case's legal-stay date
        self.assertNotIn("15.01.2027", notes)   # not the study case's

    def test_legacy_null_case_on_multi_case_client_does_not_guess(self) -> None:
        reminder = self._legal_stay_reminder(self.work_case)
        # Simulate a legacy row that predates case-scoping.
        Reminder.objects.filter(pk=reminder.pk).update(case=None)
        reminder.refresh_from_db()
        notes = reminder.display_notes
        # Ambiguous (2 cases, no case on reminder): must not pick an arbitrary MOS.
        self.assertNotIn("31.07.2026", notes)
        self.assertNotIn("15.01.2027", notes)
