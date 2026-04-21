from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

from clients.services.email_campaigns import process_campaign, process_pending_email_campaigns

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Process queued mass email campaigns."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of pending campaigns to process in one run.",
        )
        parser.add_argument(
            "--campaign-id",
            type=int,
            default=None,
            help="Process one specific pending campaign by id.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        campaign_id = options["campaign_id"]

        if campaign_id is not None:
            logger.info("Processing queued email campaign %s", campaign_id)
            result = process_campaign(campaign_id)
            if result is None:
                logger.info("Email campaign %s was not processed (missing or not pending)", campaign_id)
                self.stdout.write(self.style.WARNING(f"Campaign {campaign_id} not found or not pending."))
                return

            self.stdout.write(
                self.style.SUCCESS(
                    f"Campaign {result.campaign_id}: {result.status}, "
                    f"sent={result.sent_count}, failed={result.failed_count}"
                )
            )
            return

        logger.info("Starting queued email campaign processing (limit=%s)", limit)
        results = process_pending_email_campaigns(limit=limit)
        if not results:
            logger.info("No pending email campaigns found")
            self.stdout.write("No pending email campaigns found.")
            return

        for result in results:
            logger.info(
                "Email campaign %s processed: status=%s sent=%s failed=%s",
                result.campaign_id,
                result.status,
                result.sent_count,
                result.failed_count,
            )
            self.stdout.write(
                f"Campaign {result.campaign_id}: {result.status}, "
                f"sent={result.sent_count}, failed={result.failed_count}"
            )

        self.stdout.write(self.style.SUCCESS(f"Processed {len(results)} email campaign(s)."))
