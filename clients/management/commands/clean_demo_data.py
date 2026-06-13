from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from clients.demo.demo_cleanup import cleanup_demo_data
from clients.demo.demo_runner import democenter_lock


class Command(BaseCommand):
    help = "Delete only Demo Center records marked as demo data."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required confirmation flag.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not getattr(settings, "DEMO_MODE_ENABLED", False):
            raise CommandError("Demo Center is disabled.")
        if not options["confirm"]:
            raise CommandError("Refusing cleanup without --confirm.")

        try:
            with democenter_lock():
                report = cleanup_demo_data()
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc
            
        self.stdout.write(self.style.SUCCESS("Demo data cleanup completed."))
        for key, val in sorted(report.items()):
            self.stdout.write(f"{key}: {val}")
