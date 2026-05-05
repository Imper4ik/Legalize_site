import os
import shutil
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from django.utils import timezone


class CleanupDatabaseMediaTempTests(SimpleTestCase):
    def setUp(self):
        self.temp_root = Path(settings.BASE_DIR) / "scratch" / "test_cleanup_temp"
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.max_age_hours = 24

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def _create_file(self, filename, age_hours):
        file_path = self.temp_root / filename
        file_path.write_text("test")
        
        mtime = (timezone.now() - timedelta(hours=age_hours)).timestamp()
        os.utime(file_path, (mtime, mtime))
        return file_path

    def _run_command(self, **kwargs):
        out = StringIO()
        with override_settings(
            DATABASE_MEDIA_TEMP_ROOT=str(self.temp_root),
            DATABASE_MEDIA_TEMP_MAX_AGE_HOURS=self.max_age_hours,
        ):
            call_command("cleanup_database_media_temp", stdout=out, **kwargs)
        return out.getvalue()

    def test_dry_run_does_not_delete_old_files(self):
        file_path = self._create_file("old.pdf", age_hours=25)
        
        output = self._run_command(dry_run=True)
        
        self.assertTrue(file_path.exists())
        self.assertIn("Would delete", output)

    def test_deletes_old_files(self):
        file_path = self._create_file("old.pdf", age_hours=25)
        
        output = self._run_command()
        
        self.assertFalse(file_path.exists())
        self.assertIn("Deleted", output)

    def test_keeps_recent_files(self):
        file_path = self._create_file("new.pdf", age_hours=23)
        
        output = self._run_command()
        
        self.assertTrue(file_path.exists())
        self.assertIn("Deleted 0 files", output)
        self.assertNotIn("new.pdf", output)

    def test_safety_does_not_delete_outside_temp_root(self):
        outside_file = self.temp_root.parent / "outside.txt"
        outside_file.write_text("test")
        
        mtime = (timezone.now() - timedelta(hours=25)).timestamp()
        os.utime(outside_file, (mtime, mtime))

        try:
            self._run_command()
            self.assertTrue(outside_file.exists())
        finally:
            outside_file.unlink(missing_ok=True)
