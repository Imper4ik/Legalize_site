from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class TranslationStage7PermissionTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.superuser = user_model.objects.create_superuser(
            username="super2", email="super2@example.com", password="pass"
        )
        self.staff = user_model.objects.create_user(
            username="staff2", email="staff2@example.com", password="pass", is_staff=True
        )

    def test_dashboard_redirects_anonymous_user_to_login(self):
        response = self.client.get(reverse("translations:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_update_api_rejects_get_for_superuser(self):
        self.client.login(username="super2", password="pass")

        response = self.client.get(reverse("translations:update_api"))

        self.assertEqual(response.status_code, 405)
        payload = response.json()
        self.assertEqual(payload["status"], "error")

    def test_update_api_handles_invalid_json_body(self):
        self.client.login(username="super2", password="pass")

        with patch("translations.views.save_translation_entry") as save_mock:
            response = self.client.post(
                reverse("translations:update_api"),
                data="not-json",
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        save_mock.assert_called_once_with(None, ru=None, en=None, pl=None)

    def test_scan_api_normalizes_whitespace_keys(self):
        self.client.login(username="super2", password="pass")

        rows = [{"msgid": "Hello   world", "ru": "Привет   мир", "en": "Hello world", "pl": "Czesc   swiecie"}]
        with patch("translations.views.load_all_translations", return_value=rows):
            response = self.client.get(reverse("translations:scan_api"))

        self.assertEqual(response.status_code, 200)
        mapping = response.json()["data"]
        self.assertIn("Hello world", mapping)
        self.assertEqual(mapping["Hello world"], "Hello   world")

    def test_non_superuser_cannot_toggle_studio(self):
        self.client.login(username="staff2", password="pass")

        response = self.client.get(reverse("translations:toggle_studio"), HTTP_REFERER="/staff/")

        self.assertEqual(response.status_code, 302)
        # denied by user_passes_test, should not set flag
        self.assertNotIn("studio_mode", self.client.session)
