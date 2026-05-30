from __future__ import annotations

from typing import Any

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.management.base import BaseCommand

from database_media.models import DatabaseMediaFile


class Command(BaseCommand):
    help = "Export PostgreSQL-backed media files to the local file system (or default storage)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be exported without writing local files.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Overwrite existing files in target storage.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = options["dry_run"]
        overwrite = options["overwrite"]

        target_storage = FileSystemStorage()
        exported = skipped = 0

        # Query all records from the PostgreSQL-backed media table
        db_files = DatabaseMediaFile.objects.all()

        for db_file in db_files.iterator():
            name = db_file.name
            
            # Check if target file already exists
            if target_storage.exists(name) and not overwrite:
                skipped += 1
                self.stdout.write(f"skipped (already exists): {name}")
                continue

            if dry_run:
                exported += 1
                self.stdout.write(f"would export: {name}")
                continue

            # Write database bytes back into standard file system storage
            file_data = bytes(db_file.content)
            if overwrite and target_storage.exists(name):
                target_storage.delete(name)
                
            target_storage.save(name, ContentFile(file_data, name=name))
            exported += 1
            self.stdout.write(self.style.SUCCESS(f"exported: {name}"))

        verb = "would export" if dry_run else "exported"
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {verb}={exported}, skipped={skipped}."
            )
        )
