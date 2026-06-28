"""ZUS RCA completeness is per-month: the checklist row must not show green
while a required month is still missing, even if some months are uploaded.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.test import TestCase

from clients.constants import DocumentType
from clients.testing.factories import create_test_client, create_test_document, create_test_user

ZUS = DocumentType.ZUS_RCA_OR_INSURANCE.value


def _month_start(d: date) -> date:
    return d.replace(day=1)


class ZusChecklistCompletenessTests(TestCase):
    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(first_name="Zus", last_name="Gap")
        self.case = self.client_obj.cases.get()

    def _zus_row(self):
        rows = {r["code"]: r for r in self.client_obj.get_document_checklist(case=self.case)}
        return rows.get(ZUS)

    def test_missing_month_keeps_row_incomplete(self) -> None:
        today = date.today()
        # Fingerprints a few months ago → several months are expected.
        self.case.workflow_stage = "waiting_decision"
        self.case.fingerprints_date = today - timedelta(days=120)
        self.case.save(update_fields=["workflow_stage", "fingerprints_date"])

        # Only one ZUS month uploaded (verified) → at least one is still missing.
        doc = create_test_document(
            self.client_obj, case=self.case, doc_type=ZUS,
            zus_period_month=_month_start(today - timedelta(days=120)),
        )
        doc.verified = True
        doc.save(update_fields=["verified"])

        row = self._zus_row()
        self.assertIsNotNone(row)
        self.assertTrue(row["is_uploaded"])
        self.assertGreaterEqual(row["zus_missing_count"], 1)
        # Must NOT be green while a month is missing.
        self.assertFalse(row["is_complete"])

    def test_non_waiting_case_is_not_flagged(self) -> None:
        # Outside waiting_decision ZUS RCA is not required, so one upload is fine.
        self.case.workflow_stage = "document_collection"
        self.case.fingerprints_date = None
        self.case.save(update_fields=["workflow_stage", "fingerprints_date"])

        doc = create_test_document(
            self.client_obj, case=self.case, doc_type=ZUS,
            zus_period_month=_month_start(date.today()),
        )
        doc.verified = True
        doc.save(update_fields=["verified"])

        row = self._zus_row()
        self.assertIsNotNone(row)
        self.assertEqual(row["zus_missing_count"], 0)
        self.assertTrue(row["is_complete"])
