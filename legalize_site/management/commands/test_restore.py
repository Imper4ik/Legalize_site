from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def _backup_directory() -> Path:
    configured = os.environ.get("DB_BACKUP_DIR")
    return Path(configured) if configured else Path(settings.BASE_DIR) / "tmp" / "db_backups"


def _latest_backup(backup_dir: Path) -> Path:
    candidates = sorted(
        path
        for path in backup_dir.glob("backup-*.sql*")
        if path.is_file() and path.name.endswith((".sql", ".sql.enc"))
    )
    if not candidates:
        raise CommandError(f"No .sql or .sql.enc backups found in {backup_dir}.")
    return candidates[-1]


def _database_identity(database_url: str) -> tuple[str, int | None, str]:
    parsed = urlsplit(database_url)
    return parsed.hostname or "", parsed.port, parsed.path.rstrip("/")


def _decrypt_backup(backup_path: Path) -> bytes:
    encrypted = backup_path.read_bytes()
    keys = list(getattr(settings, "FERNET_KEYS", []))
    if not keys:
        raise CommandError("Encrypted backup found but FERNET_KEYS is not configured.")

    for key in keys:
        key_bytes = key.encode() if isinstance(key, str) else key
        try:
            return Fernet(key_bytes).decrypt(encrypted)
        except (InvalidToken, ValueError):
            continue
    raise CommandError("Encrypted backup cannot be decrypted with any configured FERNET_KEYS value.")


class Command(BaseCommand):
    help = "Restore the latest backup into an explicitly configured disposable PostgreSQL database."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--backup", help="Path to a specific .sql or .sql.enc backup artifact.")
        parser.add_argument(
            "--database-url",
            help="Disposable restore target. Defaults to RESTORE_TEST_DATABASE_URL.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        backup_path = Path(options.get("backup") or "") if options.get("backup") else _latest_backup(_backup_directory())
        if not backup_path.is_file():
            raise CommandError(f"Backup file not found: {backup_path}")

        target_url = (options.get("database_url") or os.environ.get("RESTORE_TEST_DATABASE_URL") or "").strip()
        if not target_url:
            raise CommandError(
                "RESTORE_TEST_DATABASE_URL (or --database-url) must point to a disposable empty PostgreSQL database."
            )

        production_url = (os.environ.get("DATABASE_URL") or os.environ.get("RAILWAY_DATABASE_URL") or "").strip()
        if production_url and _database_identity(target_url) == _database_identity(production_url):
            raise CommandError("Refusing to restore into the configured production database.")

        psql_path = shutil.which("psql")
        if not psql_path:
            raise CommandError("psql command not found in system PATH.")

        with tempfile.TemporaryDirectory(prefix="legalize-restore-") as temp_dir:
            if backup_path.name.endswith(".sql.enc"):
                sql_path = Path(temp_dir) / "restore.sql"
                sql_path.write_bytes(_decrypt_backup(backup_path))
                try:
                    os.chmod(sql_path, 0o600)
                except OSError:
                    pass
            else:
                sql_path = backup_path

            if sql_path.stat().st_size == 0:
                raise CommandError("Backup artifact is empty.")

            try:
                subprocess.run(  # nosec B603
                    [
                        psql_path,
                        target_url,
                        "--set",
                        "ON_ERROR_STOP=1",
                        "--single-transaction",
                        "--file",
                        str(sql_path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                probe = subprocess.run(  # nosec B603
                    [
                        psql_path,
                        target_url,
                        "--tuples-only",
                        "--no-align",
                        "--set",
                        "ON_ERROR_STOP=1",
                        "--command",
                        "SELECT COUNT(*) FROM django_migrations;",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as exc:
                raise CommandError(
                    "Restore verification failed. The target must be an empty disposable database; "
                    "inspect PostgreSQL logs for details."
                ) from exc

        try:
            migration_count = int(probe.stdout.strip())
        except ValueError as exc:
            raise CommandError("Restore probe returned an invalid migration count.") from exc
        if migration_count <= 0:
            raise CommandError("Restore completed but no Django migration history was found.")

        self.stdout.write(
            self.style.SUCCESS(
                f"Restore verified from {backup_path.name}: {migration_count} migration rows found in the disposable target."
            )
        )
