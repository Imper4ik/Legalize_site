from django.core.management.base import BaseCommand

from clients.constants import DocumentType
from clients.models import DocumentRequirement, is_default_document_label


class Command(BaseCommand):
    help = "Normalize document requirement custom names to default translations."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many records would be updated without saving changes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        doc_type_values = {choice.value for choice in DocumentType}
        queryset = DocumentRequirement.objects.exclude(custom_name__isnull=True).exclude(custom_name__exact="")
        total = queryset.count()
        updated = 0

        for requirement in queryset.iterator():
            if requirement.document_type not in doc_type_values:
                continue
            if not is_default_document_label(requirement.custom_name, requirement.document_type):
                continue
            updated += 1
            if dry_run:
                continue
            requirement.custom_name = None
            requirement.save(update_fields=["custom_name"])

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[dry-run] Would normalize {updated} of {total} custom document names."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Normalized {updated} of {total} custom document names.")
            )
