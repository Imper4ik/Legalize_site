from __future__ import annotations

import os
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse


class CronSecretIsolationTests(TestCase):
    @patch.dict(os.environ, {"BACKUP_TRIGGER_SECRET": "legacy-backup-secret"}, clear=True)
    @patch("legalize_site.cron_views.process_pending_email_campaigns")
    def test_legacy_backup_secret_cannot_run_non_backup_cron(self, process_mock):
        response = self.client.post(
            reverse("process_email_campaigns_cron"),
            HTTP_AUTHORIZATION="Bearer legacy-backup-secret",
            REMOTE_ADDR="127.0.0.1",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "forbidden"})
        process_mock.assert_not_called()
