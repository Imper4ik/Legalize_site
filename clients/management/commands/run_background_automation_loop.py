from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from django.core.cache import cache
from django.core.management import BaseCommand, call_command
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run background automation tasks for OCR jobs, email campaigns, and weekly reminders."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Keep running automation cycles until the process is stopped.",
        )
        parser.add_argument(
            "--interval-seconds",
            type=int,
            default=300,
            help="How often the loop runs OCR and email campaign processing.",
        )
        parser.add_argument(
            "--document-job-limit",
            type=int,
            default=50,
            help="Maximum queued OCR jobs to process in one cycle.",
        )
        parser.add_argument(
            "--email-campaign-limit",
            type=int,
            default=50,
            help="Maximum queued email campaigns to process in one cycle.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        loop = bool(options["loop"])
        interval_seconds = max(60, int(options["interval_seconds"]))

        while True:
            self._run_cycle(
                interval_seconds=interval_seconds,
                document_job_limit=max(1, min(100, int(options["document_job_limit"]))),
                email_campaign_limit=max(1, min(100, int(options["email_campaign_limit"]))),
            )
            if not loop:
                return
            time.sleep(interval_seconds)

    def _run_cycle(
        self,
        *,
        interval_seconds: int,
        document_job_limit: int,
        email_campaign_limit: int,
    ) -> None:
        self._run_locked(
            "document-jobs",
            timeout=interval_seconds,
            task=lambda: call_command("process_document_jobs", "--limit", str(document_job_limit)),
        )
        self._run_locked(
            "email-campaigns",
            timeout=interval_seconds,
            task=lambda: call_command("process_email_campaigns", "--limit", str(email_campaign_limit)),
        )
        self._run_locked(
            "weekly-document-reminders",
            timeout=interval_seconds,
            task=lambda: call_command("run_weekly_document_reminders"),
        )

    def _run_locked(self, name: str, *, timeout: int, task: Callable[[], Any]) -> bool:
        cache_key = f"background_automation_loop:{name}"
        try:
            acquired = cache.add(cache_key, timezone.now().isoformat(), timeout=timeout)
        except Exception:
            logger.warning("Automation lock failed for %s; running task anyway.", name, exc_info=True)
            acquired = True

        if not acquired:
            logger.info("Skipping %s because another automation loop holds the lock.", name)
            return False

        try:
            task()
            return True
        except Exception:
            logger.exception("Background automation task failed: %s", name)
            return False
        finally:
            try:
                cache.delete(cache_key)
            except Exception:
                logger.warning("Failed to release automation lock for %s.", name, exc_info=True)
