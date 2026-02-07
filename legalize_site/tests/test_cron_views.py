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
            with patch("legalize_site.cron_views.subprocess.run") as mocked_run:
                response = self.client.post("/cron/db-backup/", HTTP_X_CRON_TOKEN="secret")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "backup done")
        self.assertTrue(payload["path"].startswith("/tmp/backup-"))
        self.assertTrue(payload["path"].endswith(".sql"))

        args, kwargs = mocked_run.call_args
        self.assertEqual(args[0][0], "pg_dump")
        self.assertEqual(args[0][1], "postgresql://postgres:pass@localhost:5432/app")
        self.assertEqual(args[0][2], "-f")
        self.assertEqual(args[0][3], payload["path"])
        self.assertTrue(kwargs["check"])
