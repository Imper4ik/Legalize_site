from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from django.core.management.base import BaseCommand, CommandError

from clients.testing.e2e_runner import available_modes, run_e2e_scenarios


class Command(BaseCommand):
    help = "Run protected Test Center E2E business scenarios."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--mode",
            choices=available_modes(),
            default="smoke",
            help="Scenario group to run.",
        )
        parser.add_argument(
            "--keep-data",
            action="store_true",
            help="Keep generated is_test_data records for debugging.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            test_run = run_e2e_scenarios(
                mode=str(options["mode"]),
                cleanup=not bool(options["keep_data"]),
            )
        except PermissionDenied as exc:
            raise CommandError(str(exc)) from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Test Run #{test_run.pk}"))
        self.stdout.write(f"Mode: {test_run.mode}")
        self.stdout.write(f"Status: {test_run.status}")
        self.stdout.write(f"Total checks: {test_run.total_checks}")
        self.stdout.write(f"Passed: {test_run.passed_checks}")
        self.stdout.write(f"Failed: {test_run.failed_checks}")
        self.stdout.write(f"Skipped: {test_run.skipped_checks}")
        if test_run.failed_checks:
            self.stdout.write(self.style.ERROR("Failed checks:"))
            for result in test_run.results.filter(status="failed").order_by("created_at"):
                self.stdout.write(f"- {result.scenario_name}: {result.error_message}")

