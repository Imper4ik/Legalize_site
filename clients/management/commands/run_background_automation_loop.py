from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.core.mail import mail_admins
from django.core.management import BaseCommand, call_command
from django.utils import timezone

logger = logging.getLogger(__name__)
HEARTBEAT_CACHE_KEY = "background_automation_loop:heartbeat"
# Long-lived marker (survives loop downtime) used to detect that the loop was
# down and has just resumed, so the owner is alerted after an outage even
# though the short-lived readiness heartbeat has already expired.
LAST_RUN_CACHE_KEY = "background_automation_loop:last_run"
LAST_RUN_TIMEOUT = 7 * 24 * 60 * 60
# Daily gate + failure-alert throttle for the optional in-process DB backup.
DB_BACKUP_DONE_KEY = "background_automation_loop:db_backup_done_date"
DB_BACKUP_DONE_TIMEOUT = 3 * 24 * 60 * 60


def _env_flag(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "true" if default else "false").lower() in {"1", "true", "yes", "on"}


class Command(BaseCommand):
    help = "Run background automation tasks for OCR jobs, email campaigns, reminders, retention and backups."

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
        heartbeat_timeout = max(180, interval_seconds * 3)
        self._check_resume_after_outage(interval_seconds=interval_seconds)
        results = {
            "document-jobs": self._run_locked(
                "document-jobs",
                timeout=interval_seconds,
                task=lambda: call_command("process_document_jobs", "--limit", str(document_job_limit)),
            ),
            "email-campaigns": self._run_locked(
                "email-campaigns",
                timeout=interval_seconds,
                task=lambda: call_command("process_email_campaigns", "--limit", str(email_campaign_limit)),
            ),
            "weekly-document-reminders": self._run_locked(
                "weekly-document-reminders",
                timeout=interval_seconds,
                task=lambda: call_command("run_weekly_document_reminders"),
            ),
            "retention-maintenance": self._run_locked(
                "retention-maintenance",
                timeout=interval_seconds,
                task=lambda: call_command("run_retention_maintenance"),
            ),
        }
        self._maybe_run_daily_backup(timeout=interval_seconds)
        failures = sorted(name for name, succeeded in results.items() if not succeeded)
        self._record_heartbeat(timeout=heartbeat_timeout, failures=failures)
        self._record_last_run()

    # --- heartbeat / outage watchdog -------------------------------------

    def _record_heartbeat(self, *, timeout: int, failures: list[str]) -> None:
        payload = {
            "status": "error" if failures else "ok",
            "checked_at": timezone.now().isoformat(),
            "failed_tasks": failures,
        }
        try:
            cache.set(HEARTBEAT_CACHE_KEY, payload, timeout=timeout)
        except Exception:
            logger.error("Failed to publish background automation heartbeat.", exc_info=True)

    def _record_last_run(self) -> None:
        try:
            cache.set(LAST_RUN_CACHE_KEY, timezone.now().isoformat(), timeout=LAST_RUN_TIMEOUT)
        except Exception:
            logger.warning("Failed to publish background automation last-run marker.", exc_info=True)

    def _check_resume_after_outage(self, *, interval_seconds: int) -> None:
        """Alert once when the loop resumes after being down for too long.

        ``/readyz`` already reports 503 while the loop is dead (external uptime
        monitors catch that live). This complements it: after the process is
        back, the long-lived last-run marker lets us measure the gap and notify
        the owner that automation was silently down for a while.
        """
        try:
            previous_raw = cache.get(LAST_RUN_CACHE_KEY)
        except Exception:
            logger.warning("Failed to read background automation last-run marker.", exc_info=True)
            return
        if not previous_raw:
            return
        previous = datetime.fromisoformat(previous_raw)
        gap_seconds = (timezone.now() - previous).total_seconds()
        threshold = max(interval_seconds * 4, 900)
        if gap_seconds <= threshold:
            return
        minutes = int(gap_seconds // 60)
        logger.error(
            "Background automation loop resumed after a %s-minute gap (was down or stalled).",
            minutes,
        )
        self._alert_admins(
            subject="[Legalize] Background automation was down",
            message=(
                f"The background automation loop resumed after being idle for about {minutes} minutes.\n"
                "During that time OCR processing, reminder/campaign emails, retention maintenance"
                " and scheduled backups did not run. Check the service logs and uptime around this window."
            ),
        )

    def _alert_admins(self, *, subject: str, message: str) -> None:
        if not getattr(settings, "CRON_FAILURE_EMAIL_ALERTS", False):
            return
        try:
            mail_admins(subject=subject, message=message, fail_silently=False)
        except Exception:
            logger.warning("Failed to send background automation admin alert.", exc_info=True)

    # --- optional in-process daily DB backup -----------------------------

    def _maybe_run_daily_backup(self, *, timeout: int) -> None:
        """Run a full DB backup once per day, in-process, when opted in.

        Enabling ``ENABLE_INPROCESS_DB_BACKUP`` removes the last hard dependency
        on an external scheduler: with it the loop backs up the database itself.
        The daily gate is set only after a *successful* backup, so a failure
        retries on the next cycle; failures raise at most one admin alert per day.
        """
        if not _env_flag("ENABLE_INPROCESS_DB_BACKUP", default=False):
            return
        today = timezone.localdate().isoformat()
        try:
            already_done = cache.get(DB_BACKUP_DONE_KEY) == today
        except Exception:
            logger.warning("Failed to read the daily DB backup marker; skipping backup this cycle.", exc_info=True)
            return
        if already_done:
            return
        self._run_locked("db-backup", timeout=timeout, task=lambda: self._run_db_backup(today=today))

    def _run_db_backup(self, *, today: str) -> None:
        from legalize_site.backups import BackupError, create_db_backup

        try:
            result = create_db_backup()
        except BackupError as exc:
            self._alert_backup_failure(today=today, error=str(exc))
            raise
        except Exception as exc:  # pragma: no cover - defensive
            self._alert_backup_failure(today=today, error=f"{exc.__class__.__name__}: {exc}")
            raise
        try:
            cache.set(DB_BACKUP_DONE_KEY, today, timeout=DB_BACKUP_DONE_TIMEOUT)
        except Exception:
            logger.warning("DB backup succeeded but the daily marker could not be stored.", exc_info=True)
        logger.info(
            "In-process daily DB backup complete: id=%s size=%s encrypted=%s remote=%s",
            result.backup_id,
            result.size_bytes,
            result.encrypted,
            result.stored_remotely,
        )

    def _alert_backup_failure(self, *, today: str, error: str) -> None:
        alert_key = f"background_automation_loop:db_backup_alert:{today}"
        try:
            first_alert_today = bool(cache.add(alert_key, "1", timeout=DB_BACKUP_DONE_TIMEOUT))
        except Exception:
            first_alert_today = True
        if not first_alert_today:
            return
        self._alert_admins(
            subject="[Legalize] Daily database backup failed",
            message=(
                "The in-process daily database backup failed and will be retried on the next cycle.\n"
                f"Error type: {error}\n"
                "Verify pg_dump availability, DATABASE_URL and backup storage configuration."
            ),
        )

    # --- shared cross-process locking ------------------------------------

    def _run_locked(self, name: str, *, timeout: int, task: Callable[[], Any]) -> bool:
        cache_key = f"background_automation_loop:{name}"
        try:
            acquired = cache.add(cache_key, timezone.now().isoformat(), timeout=timeout)
        except Exception:
            logger.error("Automation lock failed for %s; skipping task.", name, exc_info=True)
            return False

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
