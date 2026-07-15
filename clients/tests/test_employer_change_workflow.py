from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from clients.models import CaseEmployerAssignment, Client, Company, EmployerChangeCandidate, StaffTask
from clients.services.anonymization import anonymize_client
from clients.services.cases import create_case_for_client
from clients.services.employers import ensure_assignment, propose_employer, review_employer_candidate


class EmployerChangeWorkflowTests(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(first_name="Anna", last_name="Nowak", citizenship="UA")
        self.old_company = Company.objects.create(name="Old Employer sp. z o.o.", nip="5252344078")
        self.case = create_case_for_client(
            client=self.client_obj,
            application_purpose="work",
            company=self.old_company,
        )
        ensure_assignment(self.case, source="test")

    def test_same_employer_by_nip_does_not_raise_alert(self):
        candidate = propose_employer(case=self.case, name="Different OCR spelling", nip="525-234-40-78")

        self.assertIsNone(candidate)
        self.assertFalse(StaffTask.objects.filter(task_type="employer_review").exists())

    def test_new_employer_requires_confirmation_and_is_deduplicated(self):
        candidate = propose_employer(case=self.case, name="New Employer S.A.", nip="8567346215")
        duplicate = propose_employer(case=self.case, name="New Employer S.A.", nip="8567346215")

        self.assertEqual(candidate.pk, duplicate.pk)
        self.case.refresh_from_db()
        self.assertEqual(self.case.company, self.old_company)
        self.assertEqual(StaffTask.objects.filter(task_type="employer_review", status="open").count(), 1)

        review_employer_candidate(
            candidate_id=candidate.pk,
            decision="confirmed",
            actor=None,
            effective_from=date(2026, 7, 1),
        )

        self.case.refresh_from_db()
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, EmployerChangeCandidate.STATUS_CONFIRMED)
        self.assertEqual(self.case.company.nip, "8567346215")
        history = list(CaseEmployerAssignment.objects.filter(case=self.case).order_by("started_at"))
        self.assertEqual(len(history), 2)
        self.assertIsNotNone(history[0].ended_at)
        self.assertIsNone(history[1].ended_at)
        self.assertEqual(history[1].effective_from, date(2026, 7, 1))
        self.assertFalse(StaffTask.objects.filter(task_type="employer_review", status="open").exists())

    def test_same_unresolved_employer_is_deduplicated_across_sources(self):
        candidate = propose_employer(
            case=self.case,
            name="New Employer S.A.",
            nip="8567346215",
            source="client_onboarding",
        )
        duplicate = propose_employer(
            case=self.case,
            name="New Employer SA",
            nip="856-734-62-15",
            source="fingerprints_check",
        )

        self.assertEqual(candidate.pk, duplicate.pk)
        self.assertEqual(self.case.employer_change_candidates.count(), 1)

    def test_candidate_is_scoped_to_one_case(self):
        other_case = create_case_for_client(client=self.client_obj, application_purpose="work", company=self.old_company)
        propose_employer(case=self.case, name="Case One Employer", nip="1234567890")

        self.assertEqual(self.case.employer_change_candidates.count(), 1)
        self.assertEqual(other_case.employer_change_candidates.count(), 0)
        other_case.refresh_from_db()
        self.assertEqual(other_case.company, self.old_company)

    def test_archived_and_non_work_cases_are_ignored(self):
        self.case.archived_at = timezone.now()
        self.case.save(update_fields=["archived_at"])
        self.assertIsNone(propose_employer(case=self.case, name="Ignored", nip="1234567890"))

        other = create_case_for_client(client=self.client_obj, application_purpose="study")
        self.assertIsNone(propose_employer(case=other, name="Ignored", nip="1234567890"))

        closed = create_case_for_client(client=self.client_obj, application_purpose="work", workflow_stage="closed")
        self.assertIsNone(propose_employer(case=closed, name="Ignored", nip="1234567890"))

    def test_needs_info_keeps_task_open_and_can_be_reviewed_again(self):
        candidate = propose_employer(case=self.case, name="Needs Check", nip="1234567890")
        review_employer_candidate(candidate_id=candidate.pk, decision="needs_info", actor=None, note="Ask client")

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, EmployerChangeCandidate.STATUS_NEEDS_INFO)
        self.assertTrue(StaffTask.objects.filter(task_type="employer_review", status="open").exists())

        review_employer_candidate(candidate_id=candidate.pk, decision="same", actor=None)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, EmployerChangeCandidate.STATUS_SAME)

    def test_first_employer_cannot_be_marked_as_same(self):
        empty_case = create_case_for_client(client=self.client_obj, application_purpose="work")
        candidate = propose_employer(case=empty_case, name="First Employer", nip="1234567890")

        with self.assertRaises(ValidationError):
            review_employer_candidate(candidate_id=candidate.pk, decision="same", actor=None)

    def test_rodo_anonymization_removes_employer_links_and_history(self):
        propose_employer(case=self.case, name="New Employer", nip="1234567890")

        anonymize_client(self.client_obj, mark_erasure_fulfilled=True)

        self.case.refresh_from_db()
        self.assertIsNone(self.case.company_id)
        self.assertFalse(EmployerChangeCandidate.objects.filter(case=self.case).exists())
        self.assertFalse(CaseEmployerAssignment.objects.filter(case=self.case).exists())
