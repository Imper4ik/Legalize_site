from __future__ import annotations

import os
import sys
from importlib import import_module
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

BASE_PRODUCTION_ENV = {
    "DJANGO_SETTINGS_MODULE": "legalize_site.settings.production",
    "APP_ENV": "production",
    "DEBUG": "False",
    "SECRET_KEY": "test-production-secret",
    "FERNET_KEYS": "x" * 44,
    "SENTRY_TRACES_SAMPLE_RATE": "0.1",
    "ALLOWED_HOSTS": "crm.example.com",
    "CSRF_TRUSTED_ORIGINS": "https://crm.example.com",
    "RAILWAY_PUBLIC_DOMAIN": "",
    "RAILWAY_STATIC_URL": "",
    "RENDER_EXTERNAL_HOSTNAME": "",
    "REDIS_URL": "",
}


def load_production_settings(extra_env: dict[str, str] | None = None):
    env = {**BASE_PRODUCTION_ENV, **(extra_env or {})}
    with patch.dict(os.environ, env, clear=True):
        return import_production_settings_fresh()


def import_production_settings_fresh():
    sys.modules.pop("legalize_site.settings.production", None)
    sys.modules.pop("legalize_site.settings.base", None)
    return import_module("legalize_site.settings.production")


class ProductionSettingsTests(SimpleTestCase):
    def test_missing_redis_url_uses_database_cache_table(self):
        settings_module = load_production_settings(
            {"REDIS_URL": "", "DJANGO_CACHE_TABLE": "custom_cache_table"}
        )

        self.assertEqual(
            settings_module.CACHES["default"]["BACKEND"],
            "django.core.cache.backends.db.DatabaseCache",
        )
        self.assertEqual(settings_module.CACHES["default"]["LOCATION"], "custom_cache_table")

    def test_redis_url_configures_redis_cache_backend(self):
        settings_module = load_production_settings(
            {"REDIS_URL": "redis://redis.internal:6379/0"}
        )

        self.assertEqual(settings_module.REDIS_URL, "redis://redis.internal:6379/0")
        self.assertEqual(
            settings_module.CACHES["default"]["BACKEND"],
            "django.core.cache.backends.redis.RedisCache",
        )
        self.assertEqual(
            settings_module.CACHES["default"]["LOCATION"],
            "redis://redis.internal:6379/0",
        )

    def test_database_media_storage_configures_default_storage_backend(self):
        settings_module = load_production_settings(
            {
                "USE_DATABASE_MEDIA_STORAGE": "true",
                "USE_S3_MEDIA_STORAGE": "false",
            }
        )

        self.assertTrue(settings_module.USE_DATABASE_MEDIA_STORAGE)
        self.assertEqual(
            settings_module.STORAGES["default"]["BACKEND"],
            "database_media.storage.DatabaseMediaStorage",
        )

    def test_database_media_storage_and_s3_are_mutually_exclusive(self):
        with patch.dict(
            os.environ,
            {
                **BASE_PRODUCTION_ENV,
                "USE_DATABASE_MEDIA_STORAGE": "true",
                "USE_S3_MEDIA_STORAGE": "true",
            },
            clear=True,
        ):
            with self.assertRaises(ImproperlyConfigured):
                import_production_settings_fresh()

    def test_railway_domain_derives_hosts_without_hardcoded_default(self):
        settings_module = load_production_settings(
            {
                "ALLOWED_HOSTS": "",
                "CSRF_TRUSTED_ORIGINS": "",
                "RAILWAY_PUBLIC_DOMAIN": "legalize-site.example.up.railway.app",
            }
        )

        self.assertIn("legalize-site.example.up.railway.app", settings_module.ALLOWED_HOSTS)
        self.assertIn(
            "https://legalize-site.example.up.railway.app",
            settings_module.CSRF_TRUSTED_ORIGINS,
        )
        self.assertNotIn(
            "legalize-site-production-740f.up.railway.app",
            settings_module.ALLOWED_HOSTS,
        )
        self.assertEqual(settings_module.SECURE_HSTS_SECONDS, 31536000)
        self.assertTrue(settings_module.SECURE_HSTS_INCLUDE_SUBDOMAINS)
        self.assertTrue(settings_module.SECURE_HSTS_PRELOAD)
        self.assertEqual(settings_module.SECURE_REFERRER_POLICY, "strict-origin-when-cross-origin")
        self.assertEqual(settings_module.SECURE_CROSS_ORIGIN_OPENER_POLICY, "same-origin")

    def test_security_headers_are_hardcoded_to_standards(self):
        settings_module = load_production_settings()
        self.assertEqual(settings_module.SECURE_HSTS_SECONDS, 31536000)
        self.assertTrue(settings_module.SECURE_HSTS_INCLUDE_SUBDOMAINS)
        self.assertTrue(settings_module.SECURE_HSTS_PRELOAD)
        self.assertEqual(settings_module.SECURE_REFERRER_POLICY, "strict-origin-when-cross-origin")
        self.assertEqual(settings_module.SECURE_CROSS_ORIGIN_OPENER_POLICY, "same-origin")
        self.assertTrue(settings_module.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertTrue(settings_module.SESSION_COOKIE_SECURE)
        self.assertTrue(settings_module.CSRF_COOKIE_SECURE)
        self.assertIn("default-src 'self'", settings_module.LEGALIZE_CONTENT_SECURITY_POLICY)
        self.assertIn("object-src 'none'", settings_module.LEGALIZE_CONTENT_SECURITY_POLICY)
        self.assertIn("frame-ancestors 'none'", settings_module.LEGALIZE_CONTENT_SECURITY_POLICY)
        self.assertIn("https://cdn.jsdelivr.net", settings_module.LEGALIZE_CONTENT_SECURITY_POLICY)
        self.assertFalse(settings_module.LEGALIZE_CSP_REPORT_ONLY)

    def test_production_uses_single_sentry_init_with_redaction(self):
        with patch("sentry_sdk.init") as sentry_init:
            load_production_settings(
                {
                    "SENTRY_DSN": "https://public@example.com/1",
                    "SENTRY_ENVIRONMENT": "railway-production",
                    "SENTRY_TRACES_SAMPLE_RATE": "0.33",
                    "SENTRY_PROFILES_SAMPLE_RATE": "0.25",
                }
            )

        self.assertEqual(sentry_init.call_count, 1)
        kwargs = sentry_init.call_args.kwargs
        self.assertEqual(kwargs["environment"], "railway-production")
        self.assertEqual(kwargs["traces_sample_rate"], 0.33)
        self.assertEqual(kwargs["profiles_sample_rate"], 0.25)
        self.assertFalse(kwargs["send_default_pii"])
        self.assertEqual(kwargs["max_request_body_size"], "never")
        self.assertEqual(kwargs["before_send"].__name__, "_sentry_before_send")
        self.assertEqual(kwargs["before_breadcrumb"].__name__, "_sentry_before_breadcrumb")

    def test_production_requires_hosts_and_csrf_origins(self):
        with patch.dict(
            os.environ,
            {
                **BASE_PRODUCTION_ENV,
                "ALLOWED_HOSTS": "",
                "CSRF_TRUSTED_ORIGINS": "",
                "RAILWAY_PUBLIC_DOMAIN": "",
                "RAILWAY_STATIC_URL": "",
                "RENDER_EXTERNAL_HOSTNAME": "",
            },
            clear=True,
        ):
            with self.assertRaises(ImproperlyConfigured):
                import_production_settings_fresh()

    def test_production_requires_csrf_origins_when_only_allowed_hosts_is_set(self):
        with patch.dict(
            os.environ,
            {
                **BASE_PRODUCTION_ENV,
                "ALLOWED_HOSTS": "crm.example.com",
                "CSRF_TRUSTED_ORIGINS": "",
                "RAILWAY_PUBLIC_DOMAIN": "",
                "RAILWAY_STATIC_URL": "",
                "RENDER_EXTERNAL_HOSTNAME": "",
            },
            clear=True,
        ):
            with self.assertRaises(ImproperlyConfigured):
                import_production_settings_fresh()

    def test_railway_static_url_derives_host_and_origin(self):
        settings_module = load_production_settings(
            {
                "ALLOWED_HOSTS": "",
                "CSRF_TRUSTED_ORIGINS": "",
                "RAILWAY_STATIC_URL": "https://legalize-static.example.up.railway.app",
            }
        )

        self.assertIn("legalize-static.example.up.railway.app", settings_module.ALLOWED_HOSTS)
        self.assertIn(
            "https://legalize-static.example.up.railway.app",
            settings_module.CSRF_TRUSTED_ORIGINS,
        )
