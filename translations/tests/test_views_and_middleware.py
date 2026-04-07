from __future__ import annotations

import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from translations.middleware import TranslationStudioMiddleware


class TranslationViewsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.superuser = user_model.objects.create_superuser(
            username="super", email="super@example.com", password="pass"
        )
        self.staff = user_model.objects.create_user(
            username="staff", email="staff@example.com", password="pass", is_staff=True
        )

    def test_superuser_can_get_stub_for_unknown_msgid(self):
        self.client.login(username="super", password="pass")
        url = reverse("translations:get_api")

        response = self.client.get(url, {"msgid": "Missing key"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["data"]["is_new"])
        self.assertEqual(payload["data"]["msgid"], "Missing key")

    def test_missing_msgid_returns_400(self):
        self.client.login(username="super", password="pass")

        response = self.client.get(reverse("translations:get_api"))

        self.assertEqual(response.status_code, 400)

    def test_update_translation_api_saves_payload(self):
        self.client.login(username="super", password="pass")
        url = reverse("translations:update_api")


        from unittest.mock import patch

        with patch("translations.views.save_translation_entry") as save_mock:
            response = self.client.post(
                url,
                data=json.dumps(
                    {
                        "msgid": "hello",
                        "ru": "привет",
                        "en": "hello",
                        "pl": "cześć",
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        save_mock.assert_called_once_with("hello", ru="привет", en="hello", pl="cześć")

    def test_toggle_studio_mode_flips_session_flag(self):
        self.client.login(username="super", password="pass")
        url = reverse("translations:toggle_studio")

        response_1 = self.client.get(url, HTTP_REFERER="/staff/")
        self.assertEqual(response_1.status_code, 302)
        self.assertTrue(self.client.session.get("studio_mode"))

        response_2 = self.client.get(url, HTTP_REFERER="/staff/")
        self.assertEqual(response_2.status_code, 302)
        self.assertFalse(self.client.session.get("studio_mode"))

    def test_staff_page_does_not_load_overlay_without_studio_mode(self):
        self.client.login(username="super", password="pass")

        response = self.client.get(reverse("clients:client_list"))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertNotIn("/static/translations/js/translation_overlay.js", html)
        self.assertNotIn("window.__studioOverlayConfig", html)

    def test_staff_page_loads_overlay_with_studio_mode(self):
        self.client.login(username="super", password="pass")
        session = self.client.session
        session["studio_mode"] = True
        session.save()

        response = self.client.get(reverse("clients:client_list"))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("/static/translations/js/translation_overlay.js", html)
        self.assertIn("window.__studioOverlayConfig", html)

    def test_non_superuser_is_denied(self):
        self.client.login(username="staff", password="pass")

        response = self.client.get(reverse("translations:dashboard"))

        self.assertEqual(response.status_code, 302)

    def test_scan_api_returns_mapping_for_all_languages(self):
        self.client.login(username="super", password="pass")

        from unittest.mock import patch

        fake_rows = [
            {"msgid": "Hello", "ru": "Привет", "en": "Hello", "pl": "Cześć"}
        ]
        with patch("translations.views.load_all_translations", return_value=fake_rows):
            response = self.client.get(reverse("translations:scan_api"))

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["Hello"], "Hello")
        self.assertEqual(data["Привет"], "Hello")
        self.assertEqual(data["Cześć"], "Hello")


class TranslationMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_sets_studio_active_true_for_superuser_with_flag(self):
        request = self.factory.get("/any/")
        request.user = type("U", (), {"is_authenticated": True, "is_superuser": True})()
        request.session = {"studio_mode": True}

        middleware = TranslationStudioMiddleware(lambda _req: HttpResponse("ok"))
        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        from django.utils import translation

        self.assertTrue(getattr(translation, "_studio_active", False))

    def test_sets_studio_active_false_for_regular_user(self):
        request = self.factory.get("/any/?studio=1")
        request.user = type("U", (), {"is_authenticated": True, "is_superuser": False})()
        request.session = {"studio_mode": True}

        middleware = TranslationStudioMiddleware(lambda _req: HttpResponse("ok"))
        middleware(request)

        from django.utils import translation

        self.assertFalse(getattr(translation, "_studio_active", True))

    def test_injects_overlay_script_for_superuser_in_studio_mode(self):
        request = self.factory.get("/pl/staff/")
        request.user = type("U", (), {"is_authenticated": True, "is_superuser": True})()
        request.session = {"studio_mode": True}

        response = HttpResponse("<html><body><h1>ok</h1></body></html>", content_type="text/html")
        middleware = TranslationStudioMiddleware(lambda _req: response)

        result = middleware(request)
        html = result.content.decode("utf-8")

        self.assertIn("/static/translations/js/translation_overlay.js", html)
        self.assertIn("window.__studioOverlayConfig", html)


class TranslationOverlayScriptTests(TestCase):
    def test_overlay_script_reads_runtime_url_config(self):
        script_path = (
            Path(__file__).resolve().parents[1]
            / "static"
            / "translations"
            / "js"
            / "translation_overlay.js"
        )
        content = script_path.read_text(encoding="utf-8")

        self.assertIn("window.__studioOverlayConfig", content)
        self.assertIn("const urls = {", content)
        self.assertIn("dashboard: studioConfig.dashboardUrl", content)
        self.assertIn("update: studioConfig.updateUrl", content)
        self.assertIn("get: studioConfig.getUrl", content)
        self.assertIn("scan: studioConfig.scanUrl", content)
        self.assertIn("STUDIO_TARGET_SELECTOR", content)
        self.assertIn("studio-form-control", content)
        self.assertIn("studioTargetAttribute", content)
        self.assertIn("studio-clickable-container", content)
        self.assertIn("const childTarget = el.querySelector('.studio-editable, .studio-form-control');", content)
        self.assertIn("let activeLookupKeys = new Set();", content)
        self.assertIn("function syncStudioTargetIds(root = document.body)", content)
        self.assertIn("function updateLiveTranslations(msgid, translatedText)", content)
