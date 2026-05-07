from __future__ import annotations

import subprocess  # nosec B404
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from legalize_site.backups import BackupError, create_db_backup


class Command(BaseCommand):
    help = "Create a PostgreSQL backup and print its metadata."

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            backup_result = create_db_backup()
        except BackupError as exc:
            raise CommandError(str(exc)) from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or str(exc)).strip()
            raise CommandError(f"pg_dump failed: {stderr}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Backup created:\n"
                f"  id={backup_result.backup_id}\n"
                f"  size_bytes={backup_result.size_bytes}\n"
                f"  encrypted={backup_result.encrypted}\n"
                f"  stored_remotely={backup_result.stored_remotely}\n"
                f"  plaintext_sha256={backup_result.plaintext_sha256}\n"
                f"  stored_file_sha256={backup_result.stored_file_sha256}"
            )
        )
