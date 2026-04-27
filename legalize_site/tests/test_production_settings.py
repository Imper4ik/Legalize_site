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
        self.assertFalse(settings_module.SECURE_HSTS_INCLUDE_SUBDOMAINS)
        self.assertFalse(settings_module.SECURE_HSTS_PRELOAD)

    def test_hsts_settings_can_be_overridden_by_environment(self):
        settings_module = load_production_settings(
            {
                "SECURE_HSTS_SECONDS": "7200",
                "SECURE_HSTS_INCLUDE_SUBDOMAINS": "True",
                "SECURE_HSTS_PRELOAD": "True",
            }
        )

        self.assertEqual(settings_module.SECURE_HSTS_SECONDS, 7200)
        self.assertTrue(settings_module.SECURE_HSTS_INCLUDE_SUBDOMAINS)
        self.assertTrue(settings_module.SECURE_HSTS_PRELOAD)

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
