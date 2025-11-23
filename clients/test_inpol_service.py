from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from clients.services.inpol import (
    InpolCaseUpdater,
    InpolCredentials,
    InpolProceeding,
    InpolChange,
    InpolStatusRepository,
    InpolStatusWatcher,
    check_inpol_and_update_clients,
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


class InpolCaseUpdaterTests(TestCase):
    def setUp(self):
        self.repo = InpolStatusRepository()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        from clients.models import Client, InpolAccount, InpolProceedingSnapshot

        Client.objects.all().delete()
        InpolAccount.objects.all().delete()
        InpolProceedingSnapshot.objects.all().delete()

    def test_updates_client_by_case_number(self):
        from clients.models import Client

        client = Client.objects.create(
            first_name="Ivan",
            last_name="Ivanov",
            citizenship="PL",
            phone="123",
            email="ivan@example.com",
            case_number="AB-123",
        )

        proceeding = InpolProceeding(
            proceeding_id="abc",
            case_number="AB-123",
            status="decision issued",
            raw={},
        )

        updater = InpolCaseUpdater()
        updater.apply_changes([InpolChange(proceeding=proceeding, previous_status=None)])

        client.refresh_from_db()
        self.assertEqual(client.inpol_status, "decision issued")
        self.assertIsNotNone(client.inpol_updated_at)

    def test_sets_case_number_when_missing_and_email_matches(self):
        from clients.models import Client

        client = Client.objects.create(
            first_name="Anna",
            last_name="Nowak",
            citizenship="PL",
            phone="321",
            email="user@example.com",
        )

        proceeding = InpolProceeding(
            proceeding_id="xyz",
            case_number="CD-456",
            status="processing",
            raw={},
        )

        updater = InpolCaseUpdater()
        updater.apply_changes(
            [InpolChange(proceeding=proceeding, previous_status=None)],
            account_email="user@example.com",
        )

        client.refresh_from_db()
        self.assertEqual(client.case_number, "CD-456")
        self.assertEqual(client.inpol_status, "processing")

    def test_helper_runs_full_flow(self):
        from clients.models import Client

        client = Client.objects.create(
            first_name="Piotr",
            last_name="Kowalski",
            citizenship="PL",
            phone="987",
            email="piotr@example.com",
        )

        credentials = InpolCredentials(email="piotr@example.com", password="secret")
        fake_client = _FakeInpolClient(
            payloads=[{"id": "abc", "caseNumber": "EF-789", "status": "awaiting decision"}]
        )

        changes = check_inpol_and_update_clients(
            credentials,
            fake_client,
            self.repo,
        )

        self.assertEqual(len(changes), 1)

        client.refresh_from_db()
        self.assertEqual(client.case_number, "EF-789")
        self.assertEqual(client.inpol_status, "awaiting decision")


class InpolManagementCommandTests(TestCase):
    def setUp(self):
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        from clients.models import Client, InpolAccount, InpolProceedingSnapshot

        Client.objects.all().delete()
        InpolAccount.objects.all().delete()
        InpolProceedingSnapshot.objects.all().delete()

    @mock.patch.dict(
        "os.environ",
        {
            "INPOL_EMAIL": "user@example.com",
            "INPOL_PASSWORD": "secret",
            "INPOL_BASE_URL": "https://inpol.test",
        },
        clear=True,
    )
    @mock.patch("clients.management.commands.check_inpol.InpolClient")
    def test_command_outputs_changes_and_no_changes(self, client_cls):
        fake_client = client_cls.return_value
        fake_client.sign_in.return_value = None
        fake_client.fetch_active_proceedings.return_value = [
            {"id": "abc", "caseNumber": "AB-123", "status": "open"}
        ]

        out = StringIO()
        call_command("check_inpol", stdout=out)

        first_run_output = out.getvalue()
        self.assertIn("Checking inPOL for updates...", first_run_output)
        self.assertIn("AB-123", first_run_output)
        self.assertIn("open", first_run_output)

        # Second run with unchanged payload should report no changes
        out = StringIO()
        call_command("check_inpol", stdout=out)
        self.assertIn("No changes detected.", out.getvalue())

    @mock.patch.dict("os.environ", {}, clear=True)
    @mock.patch("clients.management.commands.check_inpol.InpolClient")
    def test_command_falls_back_to_active_account(self, client_cls):
        from clients.models import InpolAccount

        InpolAccount.objects.create(
            name="Prod",
            base_url="https://db.inpol",
            email="db@example.com",
            password="db-secret",
        )

        fake_client = client_cls.return_value
        fake_client.sign_in.return_value = None
        fake_client.fetch_active_proceedings.return_value = [
            {"id": "abc", "caseNumber": "AB-123", "status": "open"}
        ]

        out = StringIO()
        call_command("check_inpol", stdout=out)

        client_cls.assert_called_once_with("https://db.inpol")
        fake_client.sign_in.assert_called_once()
        creds = fake_client.sign_in.call_args[0][0]
        self.assertEqual(creds.email, "db@example.com")
        self.assertEqual(creds.password, "db-secret")
        self.assertIn("AB-123", out.getvalue())

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_command_errors_without_env_or_account(self):
        with self.assertRaisesMessage(CommandError, "Missing inPOL credentials"):
            call_command("check_inpol")


class _FakeInpolClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.signed_in_with = None

    def sign_in(self, credentials):
        self.signed_in_with = credentials
        return None

    def fetch_active_proceedings(self, endpoint: str = "api/proceedings/active-proceedings"):
        return self.payloads
