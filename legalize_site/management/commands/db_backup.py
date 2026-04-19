from __future__ import annotations

import subprocess

from django.core.management.base import BaseCommand, CommandError

from legalize_site.backups import BackupError, create_db_backup


class Command(BaseCommand):
    help = "Create a PostgreSQL backup and print its metadata."

    def handle(self, *args, **options):
        try:
            backup_result = create_db_backup()
        except BackupError as exc:
            raise CommandError(str(exc)) from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or str(exc)).strip()
            raise CommandError(f"pg_dump failed: {stderr}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Backup created: "
                f"id={backup_result.backup_id} "
                f"path={backup_result.path} "
                f"size_bytes={backup_result.size_bytes} "
                f"sha256={backup_result.sha256}"
            )
        )
