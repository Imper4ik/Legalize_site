from __future__ import annotations

from unittest.mock import patch

from django.core.checks import Error, Warning
from django.test import SimpleTestCase, override_settings

from legalize_site.checks import (
    BACKUP_STORAGE_WARNING_ID,
    CRON_TOKEN_ERROR_ID,
    EMAIL_CONSOLE_WARNING_ID,
    EMAIL_ERROR_ID,
    EMAIL_WARNING_ID,
    FERNET_KEYS_ERROR_ID,
    MEDIA_STORAGE_ERROR_ID,
    RATE_LIMIT_CACHE_ERROR_ID,
    RUNTIME_DEPENDENCY_WARNING_ID,
    SECRET_KEY_ERROR_ID,
    TRANSLATION_TOOLING_WARNING_ID,
    UPLOAD_LIMIT_ERROR_ID,
    cron_token_check,
    email_configuration_check,
    encryption_configuration_check,
    production_storage_safety_check,
    rate_limit_cache_check,
    runtime_dependency_check,
    translation_tooling_check,
    upload_policy_check,
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
    @override_settings(
        IS_PRODUCTION=True,
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    )
    def test_production_errors_without_shared_cache(self):
        messages = rate_limit_cache_check()

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Error)
        self.assertEqual(messages[0].id, RATE_LIMIT_CACHE_ERROR_ID)
        self.assertEqual(
            messages[0].msg,
            "Production rate limits need a shared cache backend.",
        )

    @override_settings(
        IS_PRODUCTION=True,
        CACHES={"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache"}},
    )
    def test_production_redis_cache_silences_rate_limit_warning(self):
        self.assertEqual(rate_limit_cache_check(), [])

    @override_settings(
        IS_PRODUCTION=True,
        CACHES={"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache"}},
    )
    def test_production_database_cache_silences_rate_limit_warning(self):
        self.assertEqual(rate_limit_cache_check(), [])

    @override_settings(IS_PRODUCTION=False)
    def test_non_production_does_not_warn_when_shared_cache_is_missing(self):
        self.assertEqual(rate_limit_cache_check(), [])

    @override_settings(IS_PRODUCTION=True, RATE_LIMITS={})
    def test_production_without_enabled_rate_limits_does_not_require_shared_cache(self):
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
        STORAGES={"backups": {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": {"bucket_name": "bucket"}}},
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

    @override_settings(IS_PRODUCTION=True, USE_S3_MEDIA_STORAGE=False, USE_DATABASE_MEDIA_STORAGE=True)
    @patch.dict("os.environ", {"BACKUP_REMOTE_STORAGE": "false"}, clear=False)
    def test_database_media_mvp_without_remote_backup_warns_only(self):
        messages = production_storage_safety_check()

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Warning)
        self.assertEqual(messages[0].id, BACKUP_STORAGE_WARNING_ID)

    @override_settings(
        IS_PRODUCTION=True,
        USE_S3_MEDIA_STORAGE=False,
        USE_DATABASE_MEDIA_STORAGE=True,
        BACKUP_STORAGE_ALIAS="backups",
        STORAGES={
            "default": {"BACKEND": "database_media.storage.DatabaseMediaStorage"},
            "backups": {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": {}},
        },
    )
    @patch.dict("os.environ", {"BACKUP_REMOTE_STORAGE": "true"}, clear=False)
    def test_remote_backup_storage_requires_bucket(self):
        messages = production_storage_safety_check()

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Error)
        self.assertEqual(messages[0].id, MEDIA_STORAGE_ERROR_ID)
        self.assertEqual(messages[0].msg, "Remote database backup storage has no bucket configured.")

    @override_settings(
        IS_PRODUCTION=True,
        USE_S3_MEDIA_STORAGE=False,
        BACKUP_STORAGE_ALIAS="backups",
        STORAGES={"backups": {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": {"bucket_name": "bucket"}}},
    )
    @patch.dict(
        "os.environ",
        {"ALLOW_PRODUCTION_LOCAL_MEDIA": "true", "BACKUP_REMOTE_STORAGE": "true"},
        clear=False,
    )
    def test_explicit_local_media_acknowledgement_silences_media_storage_error(self):
        self.assertEqual(production_storage_safety_check(), [])

class CronAllowedIpsCheckTests(SimpleTestCase):
    @override_settings(IS_PRODUCTION=True)
    @patch.dict("os.environ", {"CRON_TOKEN": "secret", "CRON_ALLOWED_IPS": ""}, clear=True)
    def test_empty_cron_allowed_ips_returns_warning(self):
        from legalize_site.checks import cron_allowed_ips_check

        messages = cron_allowed_ips_check()
        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Warning)
        self.assertEqual(messages[0].id, "legalize_site.W009")
        self.assertIn("CRON_ALLOWED_IPS is empty", messages[0].msg)

    @override_settings(IS_PRODUCTION=True)
    @patch.dict("os.environ", {"CRON_TOKEN": "secret", "CRON_ALLOWED_IPS": "127.0.0.1"}, clear=True)
    def test_configured_cron_allowed_ips_returns_no_warnings(self):
        from legalize_site.checks import cron_allowed_ips_check

        self.assertEqual(cron_allowed_ips_check(), [])


class CronTokenCheckTests(SimpleTestCase):
    @override_settings(IS_PRODUCTION=True)
    @patch.dict("os.environ", {"CRON_TOKEN": ""}, clear=True)
    def test_production_requires_cron_token(self):
        messages = cron_token_check()

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Error)
        self.assertEqual(messages[0].id, CRON_TOKEN_ERROR_ID)

    @override_settings(IS_PRODUCTION=True)
    @patch.dict("os.environ", {"CRON_TOKEN": "secret"}, clear=True)
    def test_configured_cron_token_has_no_messages(self):
        self.assertEqual(cron_token_check(), [])


class TranslationToolingCheckTests(SimpleTestCase):
    @override_settings(IS_PRODUCTION=True, ENABLE_TRANSLATION_TOOLING=True)
    def test_production_translation_tooling_returns_warning(self):
        messages = translation_tooling_check()

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Warning)
        self.assertEqual(messages[0].id, TRANSLATION_TOOLING_WARNING_ID)

    @override_settings(IS_PRODUCTION=True, ENABLE_TRANSLATION_TOOLING=False)
    def test_disabled_production_translation_tooling_has_no_messages(self):
        self.assertEqual(translation_tooling_check(), [])

    @override_settings(IS_PRODUCTION=False, ENABLE_TRANSLATION_TOOLING=True)
    def test_non_production_translation_tooling_has_no_messages(self):
        self.assertEqual(translation_tooling_check(), [])


class UploadPolicyCheckTests(SimpleTestCase):
    @override_settings(MAX_UPLOAD_SIZE_MB=0)
    def test_upload_size_limit_must_be_positive(self):
        messages = upload_policy_check()

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Error)
        self.assertEqual(messages[0].id, UPLOAD_LIMIT_ERROR_ID)

    @override_settings(MAX_UPLOAD_SIZE_MB=20)
    def test_valid_upload_policy_has_no_messages(self):
        self.assertEqual(upload_policy_check(), [])
