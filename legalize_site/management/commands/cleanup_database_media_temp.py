from __future__ import annotations

import os
import time
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Clean up old temporary files created by DatabaseMediaStorage."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be deleted without actually deleting files.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = options["dry_run"]
        temp_root = getattr(settings, "DATABASE_MEDIA_TEMP_ROOT", None)

        if not temp_root:
            self.stdout.write(self.style.WARNING("DATABASE_MEDIA_TEMP_ROOT is not configured. Nothing to do."))
            return

        temp_dir = Path(temp_root)
        if not temp_dir.exists() or not temp_dir.is_dir():
            self.stdout.write(self.style.WARNING(f"Temp directory does not exist: {temp_dir}"))
            return

        max_age_hours = getattr(settings, "DATABASE_MEDIA_TEMP_MAX_AGE_HOURS", 24)
        if max_age_hours <= 0:
            self.stdout.write(self.style.ERROR("DATABASE_MEDIA_TEMP_MAX_AGE_HOURS must be > 0"))
            return

        cutoff_time = time.time() - (max_age_hours * 3600)

        deleted_count = 0
        deleted_size = 0

        for root, _, files in os.walk(temp_dir):
            for filename in files:
                filepath = Path(root) / filename
                try:
                    stat = filepath.stat()
                    if stat.st_mtime < cutoff_time:
                        if not dry_run:
                            filepath.unlink()
                        deleted_count += 1
                        deleted_size += stat.st_size
                except OSError as exc:
                    self.stdout.write(self.style.ERROR(f"Error processing {filepath}: {exc}"))

        size_mb = deleted_size / (1024 * 1024)

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"[DRY-RUN] Would delete {deleted_count} files ({size_mb:.2f} MB) older than {max_age_hours} hours."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Deleted {deleted_count} files ({size_mb:.2f} MB) older than {max_age_hours} hours."
                )
            )
