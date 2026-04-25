from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


class TranslationAdminEndpointTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.superuser = user_model.objects.create_superuser(
            email="super@example.com",
            password="pass",
        )
        self.staff = user_model.objects.create_user(
            email="staff@example.com",
            password="pass",
            is_staff=True,
        )

    @override_settings(ENABLE_TRANSLATION_TOOLING=False)
    def test_flag_off_superuser_is_blocked(self):
        self.client.force_login(self.superuser)
        response = self.client.post(reverse("update_translations"))
        self.assertIn(response.status_code, {403, 404})

    @override_settings(ENABLE_TRANSLATION_TOOLING=True)
    @patch("clients.views.admin_views.call_command")
    def test_flag_on_superuser_allowed(self, call_command_mock):
        self.client.force_login(self.superuser)
        response = self.client.post(reverse("update_translations"), HTTP_REFERER="/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(call_command_mock.called)

    @override_settings(ENABLE_TRANSLATION_TOOLING=True)
    def test_flag_on_non_superuser_forbidden(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("update_translations"))
        self.assertEqual(response.status_code, 403)

    @override_settings(ENABLE_TRANSLATION_TOOLING=True)
    def test_anonymous_user_redirected_or_forbidden(self):
        response = self.client.post(reverse("update_translations"))
        self.assertIn(response.status_code, {302, 403})
