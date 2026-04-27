from __future__ import annotations

import hashlib
import posixpath
from pathlib import Path
from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage
from django.db import IntegrityError, transaction
from django.utils._os import safe_join
from django.utils.encoding import filepath_to_uri


class DatabaseMediaStorage(Storage):
    """Django storage backend that persists uploaded media bytes in PostgreSQL."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fallback_storage = FileSystemStorage(location=settings.MEDIA_ROOT, base_url=settings.MEDIA_URL)
        self.fallback_enabled = getattr(settings, "DATABASE_MEDIA_FALLBACK_TO_FILE_SYSTEM", True)
        self.auto_import_legacy_files = getattr(settings, "DATABASE_MEDIA_AUTO_IMPORT_LEGACY_FILES", True)

    def _clean_name(self, name: str) -> str:
        cleaned = str(name).replace("\\", "/").lstrip("/")
        normalized = posixpath.normpath(cleaned)
        if normalized in {"", "."} or normalized.startswith("../") or "/../" in normalized:
            raise SuspiciousFileOperation(f"Invalid database media path: {name!r}")
        return normalized

    def _model(self):
        from database_media.models import DatabaseMediaFile

        return DatabaseMediaFile

    def _read_content(self, content) -> tuple[bytes, str]:
        if hasattr(content, "seek"):
            content.seek(0)
        chunks = content.chunks() if hasattr(content, "chunks") else [content.read()]
        data = b"".join(bytes(chunk) for chunk in chunks)
        return data, getattr(content, "content_type", "") or ""

    def _create_blob(self, name: str, data: bytes, content_type: str):
        model = self._model()
        digest = hashlib.sha256(data).hexdigest()
        return model.objects.create(
            name=name,
            content=data,
            content_type=content_type,
            size=len(data),
            sha256=digest,
        )

    def _import_from_fallback(self, name: str):
        if not self.fallback_enabled or not self.auto_import_legacy_files:
            return None
        if not self.fallback_storage.exists(name):
            return None
        with self.fallback_storage.open(name, "rb") as legacy_file:
            data = legacy_file.read()
        try:
            return self._create_blob(name, data, "")
        except IntegrityError:
            return self._model().objects.filter(name=name).first()

    def _get_blob(self, name: str):
        cleaned = self._clean_name(name)
        model = self._model()
        blob = model.objects.filter(name=cleaned).first()
        if blob is not None:
            return blob
        return self._import_from_fallback(cleaned)

    def _open(self, name: str, mode: str = "rb"):
        blob = self._get_blob(name)
        if blob is None:
            raise FileNotFoundError(name)
        return ContentFile(bytes(blob.content), name=blob.name)

    def _save(self, name: str, content) -> str:
        cleaned = self._clean_name(name)
        data, content_type = self._read_content(content)
        try:
            with transaction.atomic():
                self._create_blob(cleaned, data, content_type)
        except IntegrityError:
            cleaned = self.get_available_name(cleaned)
            with transaction.atomic():
                self._create_blob(cleaned, data, content_type)
        return cleaned

    def delete(self, name: str) -> None:
        cleaned = self._clean_name(name)
        self._model().objects.filter(name=cleaned).delete()

    def exists(self, name: str) -> bool:
        cleaned = self._clean_name(name)
        if self._model().objects.filter(name=cleaned).exists():
            return True
        return self.fallback_enabled and self.fallback_storage.exists(cleaned)

    def size(self, name: str) -> int:
        blob = self._get_blob(name)
        if blob is not None:
            return blob.size
        if self.fallback_enabled:
            return self.fallback_storage.size(self._clean_name(name))
        raise FileNotFoundError(name)

    def url(self, name: str) -> str:
        return urljoin(settings.MEDIA_URL, filepath_to_uri(self._clean_name(name)))

    def path(self, name: str) -> str:
        cleaned = self._clean_name(name)
        blob = self._get_blob(cleaned)
        if blob is None:
            if self.fallback_enabled and self.fallback_storage.exists(cleaned):
                return self.fallback_storage.path(cleaned)
            raise FileNotFoundError(name)

        temp_root = Path(getattr(settings, "DATABASE_MEDIA_TEMP_ROOT"))
        target = Path(safe_join(str(temp_root), cleaned))
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.stat().st_size != blob.size:
            target.write_bytes(bytes(blob.content))
        return str(target)

    def get_created_time(self, name: str):
        blob = self._get_blob(name)
        if blob is None:
            raise FileNotFoundError(name)
        return blob.created_at

    def get_modified_time(self, name: str):
        blob = self._get_blob(name)
        if blob is None:
            raise FileNotFoundError(name)
        return blob.updated_at
