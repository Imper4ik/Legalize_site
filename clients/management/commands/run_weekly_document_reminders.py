from __future__ import annotations

import logging
import time
from typing import Any

from django.core.cache import cache
from django.core.management import BaseCommand, call_command
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run daily document/ZUS RCA/legal-stay reminder checks, optionally as a long-running loop."

    UPDATE_REMINDER_ARGS = ("--only", "missing-docs", "--only", "zus", "--only", "documents", "--only", "legal-stay", "--only", "custom-documents")

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Keep checking the daily schedule until the process is stopped.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run immediately, ignoring the daily schedule and cache guard.",
        )
        parser.add_argument(
            "--hour",
            type=int,
            default=8,
            help="Scheduled local hour in Django TIME_ZONE.",
        )
        parser.add_argument(
            "--check-interval-seconds",
            type=int,
            default=3600,
            help="How often the loop wakes up to check whether the daily run is due.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        loop = bool(options["loop"])

        while True:
            self._run_if_due(
                force=bool(options["force"]),
                hour=int(options["hour"]),
            )
            if not loop:
                return
            time.sleep(max(60, int(options["check_interval_seconds"])))

    def _run_if_due(self, *, force: bool, hour: int) -> bool:
        now = timezone.localtime()
        if not force and now.hour < hour:
            return False

        cache_key = f"daily_document_reminders:{now.date().isoformat()}"
        if not force:
            try:
                if not cache.add(cache_key, now.isoformat(), timeout=25 * 60 * 60):
                    return False
            except Exception:
                logger.warning("Daily document reminder cache guard failed; running anyway.", exc_info=True)

        logger.info("Starting daily document reminder check.")
        call_command("update_reminders", *self.UPDATE_REMINDER_ARGS)
        self.stdout.write(self.style.SUCCESS("Daily document reminder check completed."))
        return True
