from __future__ import annotations

from typing import Any


from django.core.management.base import BaseCommand, CommandError

from clients.testing.cleanup import cleanup_test_data
from clients.testing.e2e_runner import testcenter_lock


class Command(BaseCommand):
    help = "Delete only Test Center records marked as test data."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required confirmation flag.",
        )
        parser.add_argument(
            "--keep-runs",
            action="store_true",
            help="Keep TestRun/TestScenarioResult report history.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not options["confirm"]:
            raise CommandError("Refusing cleanup without --confirm.")

        try:
            with testcenter_lock():
                report = cleanup_test_data(include_test_runs=not bool(options["keep_runs"]))
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("Test data cleanup completed."))
        for label, count in sorted(report.deleted.items()):
            self.stdout.write(f"{label}: {count}")
        self.stdout.write(f"files_deleted: {report.files_deleted}")
        if report.file_errors:
            self.stdout.write(self.style.WARNING("file_errors:"))
            for error in report.file_errors:
                self.stdout.write(f"- {error}")
