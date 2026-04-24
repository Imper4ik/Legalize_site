from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from legalize_site.backups import create_db_backup


class BackupTests(SimpleTestCase):
    @override_settings(FERNET_KEYS=[])
    @patch("legalize_site.backups.shutil.which", return_value="/usr/bin/pg_dump")
    @patch("legalize_site.backups.subprocess.run")
    @patch("legalize_site.backups._backup_dir")
    def test_create_backup_has_path_and_invokes_pg_dump(self, backup_dir_mock, run_mock, _which):
        tmp_dir = Path("/tmp/legalize-test-backups")
        tmp_dir.mkdir(parents=True, exist_ok=True)
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
        tmp_dir = Path("/tmp/legalize-test-backups-log")
        tmp_dir.mkdir(parents=True, exist_ok=True)
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
        tmp_dir = Path("/tmp/legalize-test-backups-keep")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        backup_dir_mock.return_value = tmp_dir

        def _fake_run(cmd, check, capture_output, text):
            Path(cmd[-1]).write_text("-- dump --")

        run_mock.side_effect = _fake_run

        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://u:p@h/db", "BACKUP_REMOTE_STORAGE": "false"}, clear=False):
            result = create_db_backup()

        self.assertTrue(Path(result.path).exists())
