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
            help="Primary scheduled local hour in Django TIME_ZONE.",
        )
        parser.add_argument(
            "--retry-hour",
            type=int,
            default=13,
            help="Second same-day retry hour in Django TIME_ZONE. Use -1 to disable.",
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
                retry_hour=int(options["retry_hour"]),
            )
            if not loop:
                return
            time.sleep(max(60, int(options["check_interval_seconds"])))

    def _run_if_due(self, *, force: bool, hour: int, retry_hour: int = 13) -> bool:
        now = timezone.localtime()
        scheduled_hours = sorted({value for value in (hour, retry_hour) if 0 <= value <= 23})
        if not scheduled_hours:
            scheduled_hours = [hour]

        due_hour = max((value for value in scheduled_hours if now.hour >= value), default=None)
        if not force and due_hour is None:
            return False

        cache_hour = due_hour if due_hour is not None else now.hour
        cache_key = f"daily_document_reminders:{now.date().isoformat()}:{cache_hour:02d}"
        if not force:
            try:
                if not cache.add(cache_key, now.isoformat(), timeout=25 * 60 * 60):
                    return False
            except Exception:
                logger.warning("Daily document reminder cache guard failed; running anyway.", exc_info=True)

        logger.info("Starting daily document reminder check for scheduled_hour=%s.", cache_hour)
        call_command("update_reminders", *self.UPDATE_REMINDER_ARGS)
        self.stdout.write(self.style.SUCCESS("Daily document reminder check completed."))
        return True
