from __future__ import annotations

from django.core.management.base import BaseCommand

from clients.models import EmailCampaign, EmailLog


class Command(BaseCommand):
    help = "Re-save email sensitive fields to enforce encrypted-at-rest values."

    def handle(self, *args, **options):
        logs_updated = 0
        campaigns_updated = 0

        for email_log in EmailLog.objects.all().only("id", "body", "recipients", "error_message"):
            email_log.save(update_fields=["body", "recipients", "error_message"])
            logs_updated += 1

        for campaign in EmailCampaign.objects.all().only(
            "id",
            "message",
            "error_details",
            "recipient_emails",
        ):
            campaign.save(update_fields=["message", "error_details", "recipient_emails"])
            campaigns_updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Re-encrypted records: email_logs={logs_updated} email_campaigns={campaigns_updated}"
            )
        )
