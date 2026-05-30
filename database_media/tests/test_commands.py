from __future__ import annotations

import os
from pathlib import Path
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.test import TestCase, override_settings

from clients.models import Client, Document as ClientDocument
from database_media.models import DatabaseMediaFile
from database_media.storage import DatabaseMediaStorage


@override_settings(
    DATABASE_MEDIA_TEMP_ROOT="tmp/test_database_media_cmd",
    MEDIA_ROOT="tmp/test_media_cmd_root",
)
class DatabaseMediaCommandsTests(TestCase):
    def setUp(self) -> None:
        self.file_system = FileSystemStorage()
        self.db_storage = DatabaseMediaStorage()
        self.db_storage.fallback_enabled = False

        # Ensure directories exist and are clean
        self.clean_directories()

        # Create a dummy client
        self.client_obj = Client.objects.create(
            first_name="Ivan",
            last_name="Test",
            citizenship="UA",
            phone="+48999888777",
            email="ivan-test@example.com",
        )

    def tearDown(self) -> None:
        self.clean_directories()

    def clean_directories(self) -> None:
        # Clean up files created during test
        for path_str in ["tmp/test_database_media_cmd", "tmp/test_media_cmd_root"]:
            path = Path(path_str)
            if path.exists():
                for f in path.glob("**/*"):
                    if f.is_file():
                        try:
                            f.unlink()
                        except OSError:
                            pass
                try:
                    path.rmdir()
                except OSError:
                    pass

    def test_copy_and_export_commands(self) -> None:
        # 1. Create a local file in file system storage
        file_name = "documents/test_cmd_file.pdf"
        self.file_system.save(file_name, ContentFile(b"%PDF-cmd-data"))

        # Create a client document referencing it
        doc = ClientDocument.objects.create(
            client=self.client_obj,
            document_type="passport",
            file=file_name,
        )

        # Ensure it doesn't exist in the database yet
        self.assertFalse(DatabaseMediaFile.objects.filter(name=file_name).exists())

        # 2. Run copy_media_to_database_storage
        call_command("copy_media_to_database_storage")

        # Verify it now exists in the database
        self.assertTrue(DatabaseMediaFile.objects.filter(name=file_name).exists())
        db_file = DatabaseMediaFile.objects.get(name=file_name)
        self.assertEqual(bytes(db_file.content), b"%PDF-cmd-data")

        # 3. Clean local file to test the export command
        if self.file_system.exists(file_name):
            self.file_system.delete(file_name)
        self.assertFalse(self.file_system.exists(file_name))

        # 4. Run export_database_media command
        call_command("export_database_media")

        # Verify it was successfully written back to the file system
        self.assertTrue(self.file_system.exists(file_name))
        with self.file_system.open(file_name, "rb") as f:
            self.assertEqual(f.read(), b"%PDF-cmd-data")

        # 5. Test dry-run and overwrite modes
        # Overwrite with different local data
        self.file_system.delete(file_name)
        self.file_system.save(file_name, ContentFile(b"%PDF-different"))

        # Dry run shouldn't overwrite or export anything if it exists
        call_command("export_database_media", dry_run=True)
        with self.file_system.open(file_name, "rb") as f:
            self.assertEqual(f.read(), b"%PDF-different")

        # Non-overwrite run shouldn't change the existing file
        call_command("export_database_media")
        with self.file_system.open(file_name, "rb") as f:
            self.assertEqual(f.read(), b"%PDF-different")

        # Overwrite run should overwrite with the database data
        call_command("export_database_media", overwrite=True)
        with self.file_system.open(file_name, "rb") as f:
            self.assertEqual(f.read(), b"%PDF-cmd-data")
