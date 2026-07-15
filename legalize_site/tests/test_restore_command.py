from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from legalize_site.management.commands.test_restore import _decrypt_backup, _latest_backup


class RestoreCommandTests(SimpleTestCase):
    def test_latest_backup_accepts_encrypted_artifacts(self):
        with TemporaryDirectory() as temp_dir:
            backup_dir = Path(temp_dir)
            (backup_dir / "backup-20260714-010000.sql").write_text("-- old")
            latest = backup_dir / "backup-20260715-010000.sql.enc"
            latest.write_bytes(b"encrypted")

            self.assertEqual(_latest_backup(backup_dir), latest)

    def test_latest_backup_fails_when_directory_has_no_artifact(self):
        with TemporaryDirectory() as temp_dir:
            with self.assertRaises(CommandError):
                _latest_backup(Path(temp_dir))

    def test_encrypted_backup_is_decrypted_with_rotated_key(self):
        active_key = Fernet.generate_key()
        encrypted = Fernet(active_key).encrypt(b"-- restored dump")
        with TemporaryDirectory() as temp_dir:
            backup = Path(temp_dir) / "backup-20260715.sql.enc"
            backup.write_bytes(encrypted)
            with override_settings(FERNET_KEYS=[Fernet.generate_key().decode(), active_key.decode()]):
                self.assertEqual(_decrypt_backup(backup), b"-- restored dump")

    @patch("legalize_site.management.commands.test_restore.shutil.which", return_value="/usr/bin/psql")
    @patch("legalize_site.management.commands.test_restore.subprocess.run")
    def test_command_restores_and_probes_disposable_database(self, run_mock, _which):
        run_mock.side_effect = [
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="124\n", stderr=""),
        ]
        with TemporaryDirectory() as temp_dir:
            backup = Path(temp_dir) / "backup-20260715.sql"
            backup.write_text("-- PostgreSQL dump")
            with patch.dict(
                "os.environ",
                {
                    "DATABASE_URL": "postgresql://user:secret@db/prod",
                    "RESTORE_TEST_DATABASE_URL": "postgresql://user:secret@db/restore_test",
                },
                clear=False,
            ):
                call_command("test_restore", backup=str(backup))

        self.assertEqual(run_mock.call_count, 2)
        self.assertIn("--single-transaction", run_mock.call_args_list[0].args[0])
        self.assertIn("SELECT COUNT(*) FROM django_migrations;", run_mock.call_args_list[1].args[0])

    def test_command_refuses_production_database(self):
        with TemporaryDirectory() as temp_dir:
            backup = Path(temp_dir) / "backup-20260715.sql"
            backup.write_text("-- PostgreSQL dump")
            with patch.dict(
                "os.environ",
                {
                    "DATABASE_URL": "postgresql://user:secret@db/prod",
                    "RESTORE_TEST_DATABASE_URL": "postgresql://other:other@db/prod",
                },
                clear=False,
            ):
                with self.assertRaisesRegex(CommandError, "production database"):
                    call_command("test_restore", backup=str(backup))
