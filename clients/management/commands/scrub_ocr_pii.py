from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from clients.models import Document
from clients.models.document import PARSED_DATA_PII_KEYS


class Command(BaseCommand):
    help = "Scrub PII (Personally Identifiable Information) from old Document parsed_data."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be scrubbed without actually modifying data.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = options["dry_run"]

        documents = Document.objects.filter(
            parsed_data__isnull=False,
            awaiting_confirmation=False,
        )

        scrubbed_count = 0
        total_count = 0

        self.stdout.write("Scanning documents for PII in parsed_data...")

        with transaction.atomic():
            for doc in documents.iterator():
                total_count += 1

                needs_scrubbing = any(key in doc.parsed_data for key in PARSED_DATA_PII_KEYS)

                if needs_scrubbing:
                    if not dry_run:
                        doc.scrub_parsed_pii()
                        doc.save(update_fields=["parsed_data"])
                    scrubbed_count += 1

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN: {scrubbed_count} out of {total_count} documents would be scrubbed."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully scrubbed PII from {scrubbed_count} out of {total_count} documents."
                )
            )
