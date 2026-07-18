from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from legalize_site.backups import BackupError, ConfiguredBackupStorage, _backup_dir, create_db_backup


class BackupTests(SimpleTestCase):
    @contextmanager
    def _temporary_backup_dir(self):
        scratch_dir = Path(settings.BASE_DIR) / "scratch" / "test_backups"
        scratch_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir = scratch_dir / f"backup-test-{uuid4().hex}"
        tmp_dir.mkdir()
        try:
            yield str(tmp_dir)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_backup_dir_defaults_to_attached_railway_volume(self):
        with self._temporary_backup_dir() as volume_dir_name:
            with patch.dict(
                "os.environ",
                {"DB_BACKUP_DIR": "", "RAILWAY_VOLUME_MOUNT_PATH": volume_dir_name},
                clear=False,
            ):
                backup_dir = _backup_dir()

            self.assertEqual(backup_dir, Path(volume_dir_name) / "db_backups")

    @override_settings(FERNET_KEYS=[])
    @patch("legalize_site.backups.shutil.which", return_value="/usr/bin/pg_dump")
    @patch("legalize_site.backups.subprocess.run")
    @patch("legalize_site.backups._backup_dir")
    def test_create_backup_has_path_and_invokes_pg_dump(self, backup_dir_mock, run_mock, _which):
        with self._temporary_backup_dir() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            backup_dir_mock.return_value = tmp_dir

            def _fake_run(cmd, check, capture_output, text):
                output_path = Path(cmd[-1])
                output_path.write_text("-- dump --")

            run_mock.side_effect = _fake_run

            with patch.dict("os.environ", {"DATABASE_URL": "postgresql://user:pass@localhost/db"}, clear=False):
                result = create_db_backup()

            self.assertTrue(result.path)
            self.assertIn("backup-", result.path)
            run_mock.assert_called_once()
            called_cmd = run_mock.call_args[0][0]
            self.assertEqual(called_cmd[0], "/usr/bin/pg_dump")

    @patch("legalize_site.backups.logger")
    @patch("legalize_site.backups.shutil.which", return_value="/usr/bin/pg_dump")
    @patch("legalize_site.backups.subprocess.run")
    @patch("legalize_site.backups._backup_dir")
    def test_database_url_is_not_logged(self, backup_dir_mock, run_mock, _which, logger_mock):
        with self._temporary_backup_dir() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            backup_dir_mock.return_value = tmp_dir

            def _fake_run(cmd, check, capture_output, text):
                Path(cmd[-1]).write_text("-- dump --")

            run_mock.side_effect = _fake_run

            secret_url = "postgresql://secret-user:secret-pass@db.example/legalize"
            with patch.dict("os.environ", {"DATABASE_URL": secret_url}, clear=False):
                create_db_backup()

            log_output = " ".join(str(call) for call in logger_mock.method_calls)
            self.assertNotIn(secret_url, log_output)

    @patch("legalize_site.backups.shutil.which", return_value="/usr/bin/pg_dump")
    @patch("legalize_site.backups.subprocess.run")
    @patch("legalize_site.backups._backup_dir")
    def test_keeps_local_backup_when_remote_not_enabled(self, backup_dir_mock, run_mock, _which):
        with self._temporary_backup_dir() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            backup_dir_mock.return_value = tmp_dir

            def _fake_run(cmd, check, capture_output, text):
                Path(cmd[-1]).write_text("-- dump --")

            run_mock.side_effect = _fake_run

            with patch.dict("os.environ", {"DATABASE_URL": "postgresql://u:p@h/db", "BACKUP_REMOTE_STORAGE": "false"}, clear=False):
                result = create_db_backup()

            self.assertTrue(Path(result.path).exists())

    @override_settings(BACKUP_STORAGE_ALIAS="backups", BACKUP_STORAGE_LOCATION="custom/prefix")
    @patch("legalize_site.backups.storages")
    def test_configured_backup_storage_uses_configured_location(self, storages_mock):
        class DummyStorage:
            def __init__(self):
                self.saved_path = ""
                self.saved_content = b""

            def save(self, path, content):
                self.saved_path = path
                self.saved_content = content.read()
                return path

        dummy_storage = DummyStorage()
        storages_mock.__getitem__.return_value = dummy_storage

        with self._temporary_backup_dir() as tmp_dir_name:
            local_path = Path(tmp_dir_name) / "backup-test.sql"
            local_path.write_bytes(b"-- dump --")

            uploaded = ConfiguredBackupStorage().upload(local_path)

        self.assertTrue(uploaded)
        self.assertEqual(dummy_storage.saved_path, "backup-test.sql")
        self.assertEqual(dummy_storage.saved_content, b"-- dump --")

    @override_settings(FERNET_KEYS=[], BACKUP_STORAGE_ALIAS="backups")
    @patch("legalize_site.backups.storages")
    @patch("legalize_site.backups.shutil.which", return_value="/usr/bin/pg_dump")
    @patch("legalize_site.backups.subprocess.run")
    @patch("legalize_site.backups._backup_dir")
    def test_remote_upload_failure_raises_and_retains_local_backup(
        self,
        backup_dir_mock,
        run_mock,
        _which,
        storages_mock,
    ):
        class FailingStorage:
            def save(self, path, content):
                raise OSError("provider-specific failure")

        storages_mock.__getitem__.return_value = FailingStorage()

        with self._temporary_backup_dir() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            backup_dir_mock.return_value = tmp_dir

            def _fake_run(cmd, check, capture_output, text):
                Path(cmd[-1]).write_text("-- dump --")

            run_mock.side_effect = _fake_run

            with patch.dict(
                "os.environ",
                {
                    "DATABASE_URL": "postgresql://user:pass@localhost/db",
                    "BACKUP_REMOTE_STORAGE": "true",
                },
                clear=False,
            ):
                with self.assertRaisesRegex(
                    BackupError,
                    "Failed to upload database backup to remote storage; local backup retained",
                ):
                    create_db_backup()

            retained_backups = list(tmp_dir.glob("backup-*.sql"))
            self.assertEqual(len(retained_backups), 1)
            self.assertEqual(retained_backups[0].read_text(), "-- dump --")

    @override_settings(FERNET_KEYS=[])
    @patch("legalize_site.backups.shutil.which", return_value="/usr/bin/pg_dump")
    @patch("legalize_site.backups.subprocess.run")
    @patch("legalize_site.backups._backup_dir")
    def test_backup_hashes_unencrypted(self, backup_dir_mock, run_mock, _which):
        with self._temporary_backup_dir() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            backup_dir_mock.return_value = tmp_dir

            def _fake_run(cmd, check, capture_output, text):
                Path(cmd[-1]).write_text("-- dump --")

            run_mock.side_effect = _fake_run

            with patch.dict("os.environ", {"DATABASE_URL": "postgresql://user:pass@localhost/db"}, clear=False):
                result = create_db_backup()

            self.assertTrue(result.plaintext_sha256)
            self.assertTrue(result.stored_file_sha256)
            self.assertEqual(result.plaintext_sha256, result.stored_file_sha256)
            self.assertFalse(result.encrypted)

    @override_settings(FERNET_KEYS=["QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="])
    @patch("legalize_site.backups.shutil.which", return_value="/usr/bin/pg_dump")
    @patch("legalize_site.backups.subprocess.run")
    @patch("legalize_site.backups._backup_dir")
    def test_backup_hashes_encrypted(self, backup_dir_mock, run_mock, _which):
        with self._temporary_backup_dir() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            backup_dir_mock.return_value = tmp_dir

            def _fake_run(cmd, check, capture_output, text):
                Path(cmd[-1]).write_text("-- dump --")

            run_mock.side_effect = _fake_run

            with patch.dict("os.environ", {"DATABASE_URL": "postgresql://user:pass@localhost/db"}, clear=False):
                result = create_db_backup()

            self.assertTrue(result.plaintext_sha256)
            self.assertTrue(result.stored_file_sha256)
            self.assertNotEqual(result.plaintext_sha256, result.stored_file_sha256)
            self.assertTrue(result.encrypted)

