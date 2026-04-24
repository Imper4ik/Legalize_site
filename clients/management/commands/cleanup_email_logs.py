from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from clients.models import EmailCampaign, EmailLog


class Command(BaseCommand):
    help = "Clear sensitive email payloads older than retention period."

    def handle(self, *args, **options):
        retention_days = int(getattr(settings, "EMAIL_LOG_BODY_RETENTION_DAYS", 180))
        cutoff = timezone.now() - timedelta(days=retention_days)

        log_count = EmailLog.objects.filter(sent_at__lt=cutoff).exclude(body="", recipients="").update(
            body="",
            recipients="",
            error_message="",
        )
        campaign_count = EmailCampaign.objects.filter(created_at__lt=cutoff).exclude(message="").update(
            message="",
            recipient_emails=[],
            error_details="",
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Cleaned email payloads: logs={log_count} campaigns={campaign_count} cutoff={cutoff.isoformat()}"
            )
        )
