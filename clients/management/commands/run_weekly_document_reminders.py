from __future__ import annotations

import logging
import time
from typing import Any

from django.core.cache import cache
from django.core.management import BaseCommand, call_command
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run weekly document/ZUS RCA reminder checks, optionally as a long-running loop."

    UPDATE_REMINDER_ARGS = ("--only", "missing-docs", "--only", "zus", "--only", "documents")

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Keep checking the weekly schedule until the process is stopped.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run immediately, ignoring the weekly schedule and cache guard.",
        )
        parser.add_argument(
            "--weekday",
            type=int,
            default=0,
            help="Scheduled weekday, where Monday is 0 and Sunday is 6.",
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
            help="How often the loop wakes up to check whether the weekly run is due.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        loop = bool(options["loop"])

        while True:
            self._run_if_due(
                force=bool(options["force"]),
                weekday=int(options["weekday"]),
                hour=int(options["hour"]),
            )
            if not loop:
                return
            time.sleep(max(60, int(options["check_interval_seconds"])))

    def _run_if_due(self, *, force: bool, weekday: int, hour: int) -> bool:
        now = timezone.localtime()
        if not force and (now.weekday() != weekday or now.hour < hour):
            return False

        cache_key = f"weekly_document_reminders:{now.date().isoformat()}"
        if not force:
            try:
                if not cache.add(cache_key, now.isoformat(), timeout=8 * 24 * 60 * 60):
                    return False
            except Exception:
                logger.warning("Weekly document reminder cache guard failed; running anyway.", exc_info=True)

        logger.info("Starting weekly document reminder check.")
        call_command("update_reminders", *self.UPDATE_REMINDER_ARGS)
        self.stdout.write(self.style.SUCCESS("Weekly document reminder check completed."))
        return True
