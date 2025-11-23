from django.test import TestCase

from clients.services.inpol import (
    InpolCredentials,
    InpolProceeding,
    InpolStatusRepository,
    InpolStatusWatcher,
)


class InpolProceedingTests(TestCase):
    def test_fallback_keys_are_supported(self):
        payload = {
            "proceedingId": "42",
            "state": "processing",
        }

        proceeding = InpolProceeding.from_api(payload)

        self.assertEqual(proceeding.proceeding_id, "42")
        self.assertEqual(proceeding.case_number, "42")
        self.assertEqual(proceeding.status, "processing")


class InpolStatusRepositoryTests(TestCase):
    def setUp(self):
        self.repo = InpolStatusRepository()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        from clients.models import InpolProceedingSnapshot

        InpolProceedingSnapshot.objects.all().delete()

    def test_save_and_load_snapshot(self):
        proceeding = InpolProceeding(
            proceeding_id="abc",
            case_number="AB-123",
            status="open",
            raw={"id": "abc", "status": "open"},
        )

        self.repo.save_snapshot([proceeding])
        loaded = self.repo.load_all()

        self.assertIn("abc", loaded)
        self.assertEqual(loaded["abc"].case_number, "AB-123")
        self.assertEqual(loaded["abc"].status, "open")


class InpolStatusWatcherTests(TestCase):
    def setUp(self):
        self.repo = InpolStatusRepository()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        from clients.models import InpolProceedingSnapshot

        InpolProceedingSnapshot.objects.all().delete()

    def test_detects_new_and_changed_statuses(self):
        credentials = InpolCredentials(email="user@example.com", password="secret")

        client = _FakeInpolClient(
            payloads=[{"id": "abc", "caseNumber": "AB-123", "status": "open"}]
        )
        watcher = InpolStatusWatcher(client, self.repo)

        first_changes = watcher.check(credentials)
        self.assertEqual(len(first_changes), 1)
        self.assertIsNone(first_changes[0].previous_status)

        client.payloads = [
            {"id": "abc", "caseNumber": "AB-123", "status": "closed"},
            {"id": "def", "caseNumber": "CD-456", "status": "received"},
        ]

        second_changes = watcher.check(credentials)
        self.assertEqual(len(second_changes), 2)

        changes_by_case = {change.proceeding.case_number: change for change in second_changes}
        self.assertEqual(changes_by_case["AB-123"].previous_status, "open")
        self.assertIsNone(changes_by_case["CD-456"].previous_status)


class _FakeInpolClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.signed_in_with = None

    def sign_in(self, credentials):
        self.signed_in_with = credentials
        return None

    def fetch_active_proceedings(self, endpoint: str = "api/proceedings/active-proceedings"):
        return self.payloads
