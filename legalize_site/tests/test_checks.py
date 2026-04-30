from __future__ import annotations

from unittest.mock import patch

from django.core.checks import Error, Warning
from django.test import SimpleTestCase, override_settings

from legalize_site.checks import (
    EMAIL_CONSOLE_WARNING_ID,
    EMAIL_ERROR_ID,
    EMAIL_WARNING_ID,
    FERNET_KEYS_ERROR_ID,
    MEDIA_STORAGE_ERROR_ID,
    RATE_LIMIT_CACHE_ERROR_ID,
    RUNTIME_DEPENDENCY_WARNING_ID,
    SECRET_KEY_ERROR_ID,
    encryption_configuration_check,
    email_configuration_check,
    production_storage_safety_check,
    rate_limit_cache_check,
    runtime_dependency_check,
)


class EmailConfigurationCheckTests(SimpleTestCase):
    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@yourdomain.tld",
    )
    def test_console_backend_returns_two_warnings_with_placeholder_domain(self):
        messages = email_configuration_check()

        self.assertEqual(len(messages), 2)
        self.assertTrue(all(isinstance(msg, Warning) for msg in messages))
        self.assertEqual({m.id for m in messages}, {EMAIL_CONSOLE_WARNING_ID, EMAIL_WARNING_ID})

    @override_settings(
        EMAIL_BACKEND="anymail.backends.sendgrid.EmailBackend",
        ANYMAIL={},
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_sendgrid_without_api_key_returns_error(self):
        messages = email_configuration_check()

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Error)
        self.assertEqual(messages[0].id, EMAIL_ERROR_ID)

    @override_settings(
        EMAIL_BACKEND="anymail.backends.sendgrid.EmailBackend",
        ANYMAIL={"SENDGRID_API_KEY": "test-key"},
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_sendgrid_with_api_key_has_no_messages(self):
        messages = email_configuration_check()
        self.assertEqual(messages, [])

    @override_settings(
        EMAIL_BACKEND="legalize_site.mail.SafeSMTPEmailBackend",
        EMAIL_HOST="smtp.sendgrid.net",
        EMAIL_HOST_PASSWORD="",
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_smtp_without_password_returns_error(self):
        messages = email_configuration_check()

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Error)
        self.assertEqual(messages[0].id, EMAIL_ERROR_ID)

    @override_settings(
        EMAIL_BACKEND="legalize_site.mail.SafeSMTPEmailBackend",
        EMAIL_HOST="smtp.sendgrid.net",
        EMAIL_HOST_PASSWORD="secret",
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_smtp_with_password_has_no_messages(self):
        messages = email_configuration_check()
        self.assertEqual(messages, [])

    @override_settings(
        IS_PRODUCTION=True,
        SECRET_KEY="django-insecure-change-me",
        FERNET_KEYS=["configured-key"],
        FERNET_KEYS_CONFIGURED=True,
    )
    def test_production_requires_non_placeholder_secret_key(self):
        messages = encryption_configuration_check()

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Error)
        self.assertEqual(messages[0].id, SECRET_KEY_ERROR_ID)

    @override_settings(
        IS_PRODUCTION=True,
        SECRET_KEY="super-secret",
        FERNET_KEYS=["derived-fallback"],
        FERNET_KEYS_CONFIGURED=False,
    )
    def test_production_requires_explicit_fernet_keys(self):
        messages = encryption_configuration_check()

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Error)
        self.assertEqual(messages[0].id, FERNET_KEYS_ERROR_ID)


class RuntimeDependencyCheckTests(SimpleTestCase):
    @patch("legalize_site.checks.collect_runtime_dependency_statuses")
    def test_runtime_dependency_check_warns_about_missing_dependencies(self, collect_mock):
        collect_mock.return_value = [
            {
                "label": "pdf2image",
                "required_for": "OCR on PDF scans",
                "hint": "Install pdf2image.",
                "available": False,
            },
            {
                "label": "tesseract",
                "required_for": "OCR text extraction",
                "hint": "Install tesseract.",
                "available": True,
            },
        ]

        messages = runtime_dependency_check()

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Warning)
        self.assertEqual(messages[0].id, RUNTIME_DEPENDENCY_WARNING_ID)
        self.assertIn("pdf2image", messages[0].msg)

    @patch("legalize_site.checks.collect_runtime_dependency_statuses", return_value=[])
    def test_runtime_dependency_check_returns_no_messages_when_all_available(self, _collect_mock):
        self.assertEqual(runtime_dependency_check(), [])


class RateLimitCacheCheckTests(SimpleTestCase):
    @override_settings(IS_PRODUCTION=True, REDIS_URL="")
    def test_production_errors_when_redis_url_is_missing(self):
        messages = rate_limit_cache_check()

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Error)
        self.assertEqual(messages[0].id, RATE_LIMIT_CACHE_ERROR_ID)
        self.assertEqual(
            messages[0].msg,
            "REDIS_URL is not configured while production rate limits are enabled.",
        )

    @override_settings(IS_PRODUCTION=True, REDIS_URL="redis://redis.internal:6379/0")
    def test_production_redis_url_silences_rate_limit_warning(self):
        self.assertEqual(rate_limit_cache_check(), [])

    @override_settings(IS_PRODUCTION=False, REDIS_URL="")
    def test_non_production_does_not_warn_when_redis_url_is_missing(self):
        self.assertEqual(rate_limit_cache_check(), [])

    @override_settings(IS_PRODUCTION=True, REDIS_URL="", RATE_LIMITS={})
    def test_production_without_enabled_rate_limits_does_not_require_redis(self):
        self.assertEqual(rate_limit_cache_check(), [])


class ProductionStorageSafetyCheckTests(SimpleTestCase):
    @override_settings(IS_PRODUCTION=True, USE_S3_MEDIA_STORAGE=False)
    @patch.dict("os.environ", {"ALLOW_PRODUCTION_LOCAL_MEDIA": ""}, clear=False)
    def test_production_errors_without_persistent_media_storage(self):
        messages = production_storage_safety_check()

        self.assertEqual(len(messages), 2)
        media_message = next(message for message in messages if message.id == MEDIA_STORAGE_ERROR_ID)
        self.assertIsInstance(media_message, Error)
        self.assertEqual(media_message.msg, "Production media storage is not persistent.")

    @override_settings(
        IS_PRODUCTION=True,
        USE_S3_MEDIA_STORAGE=True,
        BACKUP_STORAGE_ALIAS="backups",
        STORAGES={"backups": {"BACKEND": "storages.backends.s3.S3Storage"}},
    )
    @patch.dict("os.environ", {"BACKUP_REMOTE_STORAGE": "true"}, clear=False)
    def test_s3_media_storage_silences_media_storage_error(self):
        self.assertEqual(production_storage_safety_check(), [])

    @override_settings(IS_PRODUCTION=True, USE_S3_MEDIA_STORAGE=False, USE_DATABASE_MEDIA_STORAGE=True)
    @patch.dict("os.environ", {"BACKUP_REMOTE_STORAGE": "true"}, clear=False)
    def test_database_media_storage_requires_separate_backup_storage(self):
        messages = production_storage_safety_check()

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Error)
        self.assertEqual(messages[0].id, MEDIA_STORAGE_ERROR_ID)

    @override_settings(
        IS_PRODUCTION=True,
        USE_S3_MEDIA_STORAGE=False,
        BACKUP_STORAGE_ALIAS="backups",
        STORAGES={"backups": {"BACKEND": "storages.backends.s3.S3Storage"}},
    )
    @patch.dict(
        "os.environ",
        {"ALLOW_PRODUCTION_LOCAL_MEDIA": "true", "BACKUP_REMOTE_STORAGE": "true"},
        clear=False,
    )
    def test_explicit_local_media_acknowledgement_silences_media_storage_error(self):
        self.assertEqual(production_storage_safety_check(), [])


