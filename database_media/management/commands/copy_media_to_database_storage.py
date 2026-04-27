from __future__ import annotations

from dataclasses import dataclass

from django.core.files import File
from django.core.files.storage import FileSystemStorage
from django.core.management.base import BaseCommand
from django.db.models import QuerySet

from database_media.storage import DatabaseMediaStorage


@dataclass(frozen=True)
class FileFieldRef:
    queryset: QuerySet
    field_name: str


class Command(BaseCommand):
    help = "Copy existing local media files into PostgreSQL-backed media storage."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be copied without writing database media rows.",
        )

    def handle(self, *args, **options):
        from clients.models import Document as ClientDocument
        from clients.models import DocumentVersion
        from submissions.models import Document as SubmissionDocument

        dry_run = options["dry_run"]
        refs = [
            FileFieldRef(ClientDocument.all_objects.all(), "file"),
            FileFieldRef(DocumentVersion.objects.all(), "file"),
            FileFieldRef(SubmissionDocument.all_objects.all(), "file_path"),
        ]
        source_storage = FileSystemStorage()
        target_storage = DatabaseMediaStorage()
        target_storage.fallback_enabled = False
        copied = skipped = missing = 0

        for ref in refs:
            for obj in ref.queryset.iterator():
                field = getattr(obj, ref.field_name)
                name = getattr(field, "name", "")
                if not name:
                    skipped += 1
                    continue
                if target_storage._model().objects.filter(name=name).exists():
                    skipped += 1
                    continue
                if not source_storage.exists(name):
                    missing += 1
                    self.stdout.write(self.style.WARNING(f"missing local file: {name}"))
                    continue
                if dry_run:
                    copied += 1
                    self.stdout.write(f"would copy: {name}")
                    continue
                with source_storage.open(name, "rb") as source_file:
                    target_storage.save(name, File(source_file, name=name))
                copied += 1
                self.stdout.write(self.style.SUCCESS(f"copied: {name}"))

        verb = "would copy" if dry_run else "copied"
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {verb}={copied}, skipped={skipped}, missing={missing}."
            )
        )
