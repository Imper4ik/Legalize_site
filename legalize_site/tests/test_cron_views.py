import subprocess
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings


class DbBackupCronViewTests(SimpleTestCase):
    @override_settings(ROOT_URLCONF="legalize_site.urls")
    def test_returns_403_when_token_invalid(self):
        with patch.dict("os.environ", {"CRON_TOKEN": "expected", "DATABASE_URL": "postgresql://db"}, clear=False):
            response = self.client.get("/cron/db-backup/", HTTP_X_CRON_TOKEN="wrong")

        self.assertEqual(response.status_code, 403)
        self.assertJSONEqual(response.content, {"error": "forbidden"})

    @override_settings(ROOT_URLCONF="legalize_site.urls")
    def test_returns_500_when_database_url_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            response = self.client.get("/cron/db-backup/")

        self.assertEqual(response.status_code, 500)
        self.assertJSONEqual(response.content, {"error": "DATABASE_URL is not configured"})

    @override_settings(ROOT_URLCONF="legalize_site.urls")
    def test_uses_dumpdata_fallback_when_pg_dump_is_not_available(self):
        with patch.dict(
            "os.environ",
            {
                "CRON_TOKEN": "secret",
                "DATABASE_URL": "postgresql://postgres:pass@localhost:5432/app",
                "DB_BACKUP_DIR": "/tmp",
            },
            clear=True,
        ):
            with patch("legalize_site.cron_views.shutil.which", return_value=None):
                with patch("legalize_site.cron_views.call_command") as mocked_call_command:
                    response = self.client.post("/cron/db-backup/", HTTP_X_CRON_TOKEN="secret")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "backup done")
        self.assertEqual(payload["format"], "json")
        self.assertIn("dumpdata fallback", payload["note"])
        self.assertTrue(payload["path"].startswith("/tmp/backup-"))
        self.assertTrue(payload["path"].endswith(".json"))
        mocked_call_command.assert_called_once()

    @override_settings(ROOT_URLCONF="legalize_site.urls")
    def test_returns_500_when_pg_dump_missing_and_fallback_disabled(self):
        with patch.dict(
            "os.environ",
            {
                "CRON_TOKEN": "secret",
                "DATABASE_URL": "postgresql://postgres:pass@localhost:5432/app",
                "ALLOW_JSON_BACKUP_FALLBACK": "false",
            },
            clear=True,
        ):
            with patch("legalize_site.cron_views.shutil.which", return_value=None):
                response = self.client.post("/cron/db-backup/", HTTP_X_CRON_TOKEN="secret")

        self.assertEqual(response.status_code, 500)
        self.assertJSONEqual(
            response.content,
            {
                "error": "pg_dump not found in container. Install PostgreSQL client tools.",
                "binary": "pg_dump",
            },
        )


    @override_settings(ROOT_URLCONF="legalize_site.urls")
    def test_uses_fallback_when_pg_dump_disappears_during_run(self):
        with patch.dict(
            "os.environ",
            {
                "CRON_TOKEN": "secret",
                "DATABASE_URL": "postgresql://postgres:pass@localhost:5432/app",
                "DB_BACKUP_DIR": "/tmp",
            },
            clear=True,
        ):
            with patch("legalize_site.cron_views.shutil.which", return_value="/usr/bin/pg_dump"):
                with patch("legalize_site.cron_views.subprocess.run", side_effect=FileNotFoundError()):
                    with patch("legalize_site.cron_views.call_command") as mocked_call_command:
                        response = self.client.post("/cron/db-backup/", HTTP_X_CRON_TOKEN="secret")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "backup done")
        self.assertEqual(payload["format"], "json")
        self.assertIn("execution failed", payload["note"])
        mocked_call_command.assert_called_once()

    @override_settings(ROOT_URLCONF="legalize_site.urls")
    def test_returns_500_when_pg_dump_fails(self):
        with patch.dict(
            "os.environ",
            {
                "CRON_TOKEN": "secret",
                "DATABASE_URL": "postgresql://postgres:pass@localhost:5432/app",
            },
            clear=True,
        ):
            error = subprocess.CalledProcessError(returncode=2, cmd=["pg_dump"], stderr="auth failed\n")
            with patch("legalize_site.cron_views.shutil.which", return_value="/usr/bin/pg_dump"):
                with patch("legalize_site.cron_views.subprocess.run", side_effect=error):
                    response = self.client.post("/cron/db-backup/", HTTP_X_CRON_TOKEN="secret")

        self.assertEqual(response.status_code, 500)
        self.assertJSONEqual(
            response.content,
            {"error": "pg_dump failed", "returncode": 2, "details": "auth failed"},
        )

    @override_settings(ROOT_URLCONF="legalize_site.urls")
    def test_uses_fallback_when_pg_dump_version_mismatch(self):
        with patch.dict(
            "os.environ",
            {
                "CRON_TOKEN": "secret",
                "DATABASE_URL": "postgresql://postgres:pass@localhost:5432/app",
                "DB_BACKUP_DIR": "/tmp",
            },
            clear=True,
        ):
            mismatch = subprocess.CalledProcessError(
                returncode=1,
                cmd=["pg_dump"],
                stderr="pg_dump: error: aborting because of server version mismatch\n",
            )
            with patch("legalize_site.cron_views.shutil.which", return_value="/usr/bin/pg_dump"):
                with patch("legalize_site.cron_views.subprocess.run", side_effect=mismatch):
                    with patch("legalize_site.cron_views.call_command") as mocked_call_command:
                        response = self.client.post("/cron/db-backup/", HTTP_X_CRON_TOKEN="secret")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "backup done")
        self.assertEqual(payload["format"], "json")
        self.assertIn("version mismatch", payload["note"])
        mocked_call_command.assert_called_once()

    @override_settings(ROOT_URLCONF="legalize_site.urls")
    def test_runs_pg_dump_and_returns_path(self):
        with patch.dict(
            "os.environ",
            {
                "CRON_TOKEN": "secret",
                "DATABASE_URL": "postgresql://postgres:pass@localhost:5432/app",
                "DB_BACKUP_DIR": "/tmp",
            },
            clear=True,
        ):
            with patch("legalize_site.cron_views.shutil.which", return_value="/usr/bin/pg_dump"):
                with patch("legalize_site.cron_views.subprocess.run") as mocked_run:
                    response = self.client.post("/cron/db-backup/", HTTP_X_CRON_TOKEN="secret")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "backup done")
        self.assertEqual(payload["format"], "sql")
        self.assertTrue(payload["path"].startswith("/tmp/backup-"))
        self.assertTrue(payload["path"].endswith(".sql"))

        args, kwargs = mocked_run.call_args
        self.assertEqual(args[0][0], "pg_dump")
        self.assertEqual(args[0][1], "postgresql://postgres:pass@localhost:5432/app")
        self.assertEqual(args[0][2], "-f")
        self.assertEqual(args[0][3], payload["path"])
        self.assertTrue(kwargs["check"])
        self.assertTrue(kwargs["capture_output"])
        self.assertTrue(kwargs["text"])
