from __future__ import annotations

from pathlib import Path

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from database_media.models import DatabaseMediaFile
from database_media.storage import DatabaseMediaStorage


class DatabaseMediaStorageTests(TestCase):
    @override_settings(DATABASE_MEDIA_TEMP_ROOT="tmp/test_database_media")
    def test_save_open_path_and_delete_file_from_database(self):
        storage = DatabaseMediaStorage()
        name = storage.save("documents/example.pdf", ContentFile(b"%PDF-test", name="example.pdf"))

        blob = DatabaseMediaFile.objects.get(name=name)
        self.assertEqual(bytes(blob.content), b"%PDF-test")
        self.assertEqual(blob.size, 9)
        self.assertEqual(len(blob.sha256), 64)

        with storage.open(name, "rb") as stored_file:
            self.assertEqual(stored_file.read(), b"%PDF-test")

        temp_path = Path(storage.path(name))
        self.assertTrue(temp_path.exists())
        self.assertEqual(temp_path.read_bytes(), b"%PDF-test")

        storage.delete(name)
        self.assertFalse(DatabaseMediaFile.objects.filter(name=name).exists())
        self.assertFalse(storage.exists(name))
