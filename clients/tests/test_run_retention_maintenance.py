from __future__ import annotations

from io import StringIO
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase


class RunRetentionMaintenanceTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def _run(self, *args: str) -> str:
        out = StringIO()
        call_command("run_retention_maintenance", *args, stdout=out)
        return out.getvalue()

    def test_first_run_executes_both_steps(self) -> None:
        with mock.patch(
            "clients.management.commands.run_retention_maintenance.call_command"
        ) as mocked:
            output = self._run()

        called = [call.args for call in mocked.call_args_list]
        self.assertIn(("cleanup_email_logs", "--execute", "--confirm"), called)
        self.assertIn(("anonymize_old_clients",), called)
        self.assertIn("Weekly email payload cleanup executed.", output)
        self.assertIn("Monthly anonymization report executed.", output)

    def test_second_run_is_skipped_by_cadence_guards(self) -> None:
        with mock.patch(
            "clients.management.commands.run_retention_maintenance.call_command"
        ) as mocked:
            self._run()
            output = self._run()

        self.assertEqual(mocked.call_count, 2)
        self.assertIn("skipped", output)

    def test_force_ignores_guards(self) -> None:
        with mock.patch(
            "clients.management.commands.run_retention_maintenance.call_command"
        ) as mocked:
            self._run()
            self._run("--force")

        self.assertEqual(mocked.call_count, 4)

    def test_guard_failure_fails_closed(self) -> None:
        with mock.patch(
            "clients.management.commands.run_retention_maintenance.call_command"
        ) as mocked, mock.patch(
            "clients.management.commands.run_retention_maintenance.cache.add",
            side_effect=RuntimeError("cache down"),
        ):
            output = self._run()

        mocked.assert_not_called()
        self.assertIn("skipped", output)

    def test_anonymize_report_never_passes_execute(self) -> None:
        with mock.patch(
            "clients.management.commands.run_retention_maintenance.call_command"
        ) as mocked:
            self._run("--force")

        for call in mocked.call_args_list:
            if call.args and call.args[0] == "anonymize_old_clients":
                self.assertNotIn("--execute", call.args)
                self.assertNotIn("--confirm", call.args)
