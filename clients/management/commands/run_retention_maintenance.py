from __future__ import annotations

import logging
from typing import Any

from django.core.cache import cache
from django.core.management import BaseCommand, call_command
from django.utils import timezone

logger = logging.getLogger(__name__)

EMAIL_LOG_CLEANUP_GUARD_TIMEOUT = 8 * 24 * 60 * 60
ANONYMIZE_REPORT_GUARD_TIMEOUT = 32 * 24 * 60 * 60


class Command(BaseCommand):
    help = (
        "Run scheduled data-retention maintenance: weekly email payload cleanup "
        "and a monthly GDPR anonymization report. Safe to invoke daily; internal "
        "guards keep the actual cadence."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run both maintenance steps immediately, ignoring the cadence guards.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        force = bool(options["force"])
        now = timezone.localtime()

        iso_year, iso_week, _ = now.isocalendar()
        if self._acquire_guard(f"retention_maintenance:email_logs:{iso_year}-W{iso_week:02d}",
                               EMAIL_LOG_CLEANUP_GUARD_TIMEOUT, force=force):
            # Clearing expired email payloads is idempotent and non-destructive
            # for business data (only bodies/recipients past the retention
            # window), so it is the one retention step that runs unattended.
            call_command("cleanup_email_logs", "--execute", "--confirm")
            self.stdout.write(self.style.SUCCESS("Weekly email payload cleanup executed."))
        else:
            self.stdout.write("Weekly email payload cleanup already ran for this week; skipped.")

        if self._acquire_guard(f"retention_maintenance:anonymize_report:{now.year}-{now.month:02d}",
                               ANONYMIZE_REPORT_GUARD_TIMEOUT, force=force):
            # Anonymization itself stays a manual, human-confirmed action
            # (--execute --confirm); automation only surfaces the monthly
            # report of eligible/blocked records in the logs.
            call_command("anonymize_old_clients")
            self.stdout.write(self.style.SUCCESS("Monthly anonymization report executed."))
        else:
            self.stdout.write("Monthly anonymization report already ran for this month; skipped.")

    def _acquire_guard(self, cache_key: str, timeout: int, *, force: bool) -> bool:
        if force:
            return True
        try:
            return bool(cache.add(cache_key, timezone.now().isoformat(), timeout=timeout))
        except Exception:
            # Fail closed: without a working guard a fleet of workers could
            # stampede the same maintenance step.
            logger.error("Retention maintenance guard failed for %s; skipping step.", cache_key, exc_info=True)
            return False
