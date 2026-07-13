from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess  # nosec B404
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from django.conf import settings
from django.core.files import File
from django.core.files.storage import storages

logger = logging.getLogger(__name__)

# Maximum age (in hours) for backup files.  Older files are purged
# automatically when a new backup is created.
MAX_BACKUP_AGE_HOURS = int(os.environ.get("MAX_BACKUP_AGE_HOURS", "24"))


class BackupError(RuntimeError):
    """Raised when a database backup cannot be created safely."""


@dataclass(frozen=True)
class BackupResult:
    backup_id: str
    path: str
    size_bytes: int
    plaintext_sha256: str
    stored_file_sha256: str
    encrypted: bool
    stored_remotely: bool


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql://", 1)
    return database_url


def _backup_dir() -> Path:
    configured_dir = os.environ.get("DB_BACKUP_DIR")
    backup_dir = Path(configured_dir) if configured_dir else Path(settings.BASE_DIR) / "tmp" / "db_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(backup_dir, 0o700)
    except OSError:
        pass
    return backup_dir


def _sha256_for_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as backup_file:
        for chunk in iter(lambda: backup_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _purge_old_backups(backup_dir: Path) -> int:
    """Remove backup files older than MAX_BACKUP_AGE_HOURS.  Returns count removed."""
    if MAX_BACKUP_AGE_HOURS <= 0:
        return 0
    cutoff = datetime.now(timezone.utc).timestamp() - MAX_BACKUP_AGE_HOURS * 3600
    removed = 0
    for path in backup_dir.glob("backup-*.sql*"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            pass
    if removed:
        logger.info("Purged %d old backup file(s) from %s", removed, backup_dir)
    return removed


def _encrypt_file(path: Path) -> Path:
    """Encrypt file in-place with Fernet if keys are available.  Returns new path."""
    fernet_keys = getattr(settings, "FERNET_KEYS", [])
    if not fernet_keys:
        return path

    try:
        from cryptography.fernet import Fernet
    except ImportError:
        logger.warning("cryptography library not available; skipping backup encryption")
        return path

    fernet = Fernet(fernet_keys[0].encode() if isinstance(fernet_keys[0], str) else fernet_keys[0])
    encrypted_path = path.with_suffix(".sql.enc")
    with path.open("rb") as src:
        data = src.read()
    encrypted = fernet.encrypt(data)
    with encrypted_path.open("wb") as dst:
        dst.write(encrypted)
    try:
        os.chmod(encrypted_path, 0o600)
    except OSError:
        logger.warning("Could not restrict permissions (0600) on %s", encrypted_path)
    # Remove plaintext original
    path.unlink(missing_ok=True)
    logger.info("Encrypted backup %s -> %s", path.name, encrypted_path.name)
    return encrypted_path


def _remote_storage_enabled() -> bool:
    return os.environ.get("BACKUP_REMOTE_STORAGE", "").lower() in {"1", "true", "yes", "on"}


def _cleanup_local_file(path: Path) -> None:
    """Best-effort removal of a local backup file after processing."""
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not remove local backup %s: %s", path, exc)


class BackupStorageBackend(Protocol):
    def upload(self, local_path: Path) -> bool:
        ...

class LocalBackupStorage:
    def upload(self, local_path: Path) -> bool:
        logger.info("Backup retained locally at %s", local_path)
        return False

class ConfiguredBackupStorage:
    def upload(self, local_path: Path) -> bool:
        storage_alias = getattr(settings, "BACKUP_STORAGE_ALIAS", "backups")

        try:
            backup_storage = storages[storage_alias]
            backend_class_name = backup_storage.__class__.__name__
            if "DatabaseMediaStorage" in backend_class_name:
                raise BackupError(
                    f"BACKUP_STORAGE_ALIAS ({storage_alias}) points to DatabaseMediaStorage. "
                    "Database backups cannot be stored in the database."
                )
        except BackupError:
            raise
        except Exception as exc:
            raise BackupError(
                f"BACKUP_REMOTE_STORAGE is enabled but STORAGES[{storage_alias!r}] is not configured."
            ) from exc

        try:
            with local_path.open("rb") as f:
                remote_path = local_path.name
                backup_storage.save(remote_path, File(f))
            logger.info("Successfully uploaded backup to remote storage: %s", remote_path)
            return True
        except Exception as exc:
            logger.error(
                "Failed to upload backup to remote storage (error_type=%s)",
                exc.__class__.__name__,
            )
            raise BackupError(
                "Failed to upload database backup to remote storage; local backup retained."
            ) from exc

def _get_storage_backend() -> BackupStorageBackend:
    if _remote_storage_enabled():
        return ConfiguredBackupStorage()
    return LocalBackupStorage()


def create_db_backup() -> BackupResult:
    pg_dump_path = shutil.which("pg_dump")
    if not pg_dump_path:
        raise BackupError("pg_dump command not found in system PATH")

    database_url = os.environ.get("DATABASE_URL") or os.environ.get("RAILWAY_DATABASE_URL")
    if not database_url:
        raise BackupError("DATABASE_URL is not configured")

    backup_dir = _backup_dir()

    # Purge stale backup files before creating a new one
    _purge_old_backups(backup_dir)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_name = f"backup-{timestamp}.sql"
    backup_path = backup_dir / backup_name

    # pg_dump is resolved with shutil.which and run without a shell.
    subprocess.run(  # nosec B603
        [pg_dump_path, _normalize_database_url(database_url), "-f", str(backup_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    try:
        os.chmod(backup_path, 0o600)
    except OSError:
        logger.warning("Could not restrict permissions (0600) on %s", backup_path)

    plaintext_sha256 = _sha256_for_file(backup_path)

    # Encrypt the backup if Fernet keys are available
    encrypted = False
    final_path = _encrypt_file(backup_path)
    if final_path != backup_path:
        encrypted = True

    stored_file_sha256 = _sha256_for_file(final_path)
    size_bytes = final_path.stat().st_size if final_path.exists() else 0

    storage_backend = _get_storage_backend()
    stored_remotely = storage_backend.upload(final_path)

    if stored_remotely:
        _cleanup_local_file(final_path)

    return BackupResult(
        backup_id=backup_path.stem,
        path=str(final_path),
        size_bytes=size_bytes,
        plaintext_sha256=plaintext_sha256,
        stored_file_sha256=stored_file_sha256,
        encrypted=encrypted,
        stored_remotely=stored_remotely,
    )
