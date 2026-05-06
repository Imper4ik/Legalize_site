from django.core.management.base import BaseCommand
from django.db import transaction
from clients.models import Document

class Command(BaseCommand):
    help = "Scrub PII (Personally Identifiable Information) from old Document parsed_data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be scrubbed without actually modifying data.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        
        documents = Document.objects.filter(
            parsed_data__isnull=False,
            awaiting_confirmation=False
        )

        scrubbed_count = 0
        total_count = 0

        self.stdout.write("Scanning documents for PII in parsed_data...")

        with transaction.atomic():
            for doc in documents.iterator():
                total_count += 1
                
                # Check if it already has pii_scrubbed flag
                if doc.parsed_data.get("pii_scrubbed"):
                    continue

                # Check if it has any keys to remove
                keys_to_remove = ["full_name", "first_name", "last_name", "case_number", "text", "raw_text"]
                needs_scrubbing = any(key in doc.parsed_data for key in keys_to_remove)

                if needs_scrubbing:
                    if not dry_run:
                        doc.scrub_parsed_pii()
                        doc.save(update_fields=["parsed_data"])
                    scrubbed_count += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(f"DRY RUN: {scrubbed_count} out of {total_count} documents would be scrubbed."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Successfully scrubbed PII from {scrubbed_count} out of {total_count} documents."))
