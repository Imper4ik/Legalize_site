from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from clients.models import EmailCampaign, EmailLog


class Command(BaseCommand):
    help = "Report or explicitly clear sensitive email payloads older than the retention period."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many email payloads would be cleared without modifying data.",
        )
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Actually clear eligible email payloads. Requires --confirm.",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required together with --execute to confirm the destructive operation.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = bool(options["dry_run"])
        execute = bool(options["execute"])
        confirm = bool(options["confirm"])
        if dry_run and execute:
            raise CommandError("--dry-run cannot be combined with --execute.")
        if execute and not confirm:
            raise CommandError("Refusing to clear email payloads without --confirm.")

        retention_days = int(getattr(settings, "EMAIL_LOG_BODY_RETENTION_DAYS", 180))
        cutoff = timezone.now() - timedelta(days=retention_days)
        logs_qs = EmailLog.objects.filter(sent_at__lt=cutoff).exclude(body="", recipients="")
        campaigns_qs = EmailCampaign.objects.filter(created_at__lt=cutoff).exclude(message="")
        log_count = logs_qs.count()
        campaign_count = campaigns_qs.count()

        if dry_run or not execute:
            self.stdout.write(
                self.style.SUCCESS(
                    "Report only. No email payloads were changed: "
                    f"logs={log_count} campaigns={campaign_count} cutoff={cutoff.isoformat()}. "
                    "Re-run with --execute --confirm to clear eligible payloads."
                )
            )
            return

        with transaction.atomic():
            updated_logs = logs_qs.update(
                body="",
                recipients="",
                error_message="",
            )
            updated_campaigns = campaigns_qs.update(
                message="",
                recipient_emails="[]",
                error_details="",
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Cleaned email payloads: logs={updated_logs} campaigns={updated_campaigns} cutoff={cutoff.isoformat()}"
            )
        )
