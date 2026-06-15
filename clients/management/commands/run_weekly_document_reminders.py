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
            "--minute",
            type=int,
            default=0,
            help="Primary scheduled local minute in Django TIME_ZONE.",
        )
        parser.add_argument(
            "--retry-hour",
            type=int,
            default=17,
            help="Second same-day retry hour in Django TIME_ZONE. Use -1 to disable.",
        )
        parser.add_argument(
            "--retry-minute",
            type=int,
            default=10,
            help="Second same-day retry minute in Django TIME_ZONE.",
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
                minute=int(options["minute"]),
                retry_hour=int(options["retry_hour"]),
                retry_minute=int(options["retry_minute"]),
            )
            if not loop:
                return
            time.sleep(max(60, int(options["check_interval_seconds"])))

    def _run_if_due(
        self,
        *,
        force: bool,
        hour: int,
        minute: int = 0,
        retry_hour: int = 17,
        retry_minute: int = 10,
    ) -> bool:
        now = timezone.localtime()
        configured_slots = ((hour, minute), (retry_hour, retry_minute))
        scheduled_slots = sorted(
            {
                (slot_hour, slot_minute)
                for slot_hour, slot_minute in configured_slots
                if 0 <= slot_hour <= 23 and 0 <= slot_minute <= 59
            }
        )
        if not scheduled_slots:
            scheduled_slots = [(hour, minute)]

        current_slot = (now.hour, now.minute)
        due_slot = max((slot for slot in scheduled_slots if current_slot >= slot), default=None)
        if not force and due_slot is None:
            return False

        cache_hour, cache_minute = due_slot if due_slot is not None else current_slot
        cache_key = f"daily_document_reminders:{now.date().isoformat()}:{cache_hour:02d}{cache_minute:02d}"
        if not force:
            try:
                if not cache.add(cache_key, now.isoformat(), timeout=25 * 60 * 60):
                    return False
            except Exception:
                logger.warning("Daily document reminder cache guard failed; running anyway.", exc_info=True)

        logger.info("Starting daily document reminder check for scheduled_time=%02d:%02d.", cache_hour, cache_minute)
        call_command("update_reminders", *self.UPDATE_REMINDER_ARGS)
        self.stdout.write(self.style.SUCCESS("Daily document reminder check completed."))
        return True
