from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

from clients.services.document_workflow import process_pending_document_jobs
from clients.services.notifications import (
    send_appointment_notification_email,
    send_missing_documents_email,
)
from clients.services.wezwanie_parser import parse_wezwanie

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Process queued document OCR jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of queued jobs to process in one run.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        logger.info("Starting queued OCR job processing (limit=%s)", limit)
        results = process_pending_document_jobs(
            limit=limit,
            parser=parse_wezwanie,
            send_missing_email=send_missing_documents_email,
            send_appointment_email=send_appointment_notification_email,
        )

        if not results:
            logger.info("No pending OCR jobs found")
            self.stdout.write("No pending document jobs found.")
            return

        completed = sum(1 for result in results if result.status == "completed")
        failed = sum(1 for result in results if result.status == "failed")
        skipped = sum(1 for result in results if result.status == "skipped")

        for result in results:
            logger.info(
                "OCR job %s finished with status=%s document=%s processed=%s",
                result.job.id,
                result.status,
                result.job.document_id,
                result.processed,
            )
            self.stdout.write(
                f"Job {result.job.id}: {result.status} for document {result.job.document_id}"
            )

        logger.info(
            "Processed %s OCR job(s): completed=%s failed=%s skipped=%s",
            len(results),
            completed,
            failed,
            skipped,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {len(results)} job(s): completed={completed}, failed={failed}, skipped={skipped}"
            )
        )
