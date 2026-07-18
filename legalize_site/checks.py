"""Custom system checks for the Legalize site project."""

from __future__ import annotations

import os
from typing import Any

from django.conf import settings
from django.core.checks import Error, Warning, register

from legalize_site.runtime import collect_runtime_dependency_statuses

EMAIL_ERROR_ID = "legalize_site.E001"
EMAIL_WARNING_ID = "legalize_site.W001"
EMAIL_CONSOLE_WARNING_ID = "legalize_site.W002"
EMAIL_CONSOLE_ERROR_ID = "legalize_site.E009"
SECRET_KEY_ERROR_ID = "legalize_site.E002"  # nosec B105
FERNET_KEYS_ERROR_ID = "legalize_site.E003"
SECRET_KEY_WARNING_ID = "legalize_site.W003"  # nosec B105
FERNET_KEYS_WARNING_ID = "legalize_site.W004"
RUNTIME_DEPENDENCY_WARNING_ID = "legalize_site.W005"
MEDIA_STORAGE_ERROR_ID = "legalize_site.E004"
MEDIA_STORAGE_WARNING_ID = "legalize_site.W006"
BACKUP_STORAGE_WARNING_ID = "legalize_site.W007"
RATE_LIMIT_CACHE_WARNING_ID = "legalize_site.W008"
RATE_LIMIT_CACHE_ERROR_ID = "legalize_site.E005"
# This is a system-check identifier, not a credential.
CRON_TOKEN_ERROR_ID = "legalize_site.E006"  # nosec B105
UPLOAD_LIMIT_ERROR_ID = "legalize_site.E007"
UPLOAD_TYPES_ERROR_ID = "legalize_site.E008"
TRANSLATION_TOOLING_WARNING_ID = "legalize_site.W010"
DATABASE_ENGINE_ERROR_ID = "legalize_site.E010"
ALERT_RECIPIENTS_ERROR_ID = "legalize_site.E011"
BACKUP_STORAGE_ERROR_ID = "legalize_site.E012"

BACKENDS = {
    "django.core.mail.backends.smtp.EmailBackend": {
        "mode": "smtp",
        "provider": "SendGrid",
        "env_var": "SENDGRID_API_KEY",
    },
    "anymail.backends.sendgrid.EmailBackend": {
        "mode": "api",
        "provider": "SendGrid",
        "env_var": "SENDGRID_API_KEY",
    },
    "anymail.backends.brevo.EmailBackend": {
        "mode": "api",
        "provider": "Brevo",
        "env_var": "BREVO_API_KEY",
    },
}


def _smtp_provider() -> str:
    """Return provider name inferred from EMAIL_HOST."""

    host = (settings.EMAIL_HOST or "").lower()
    if not host:
        return ""
    if "brevo" in host or "sendinblue" in host:
        return "Brevo"
    if "sendgrid" in host:
        return "SendGrid"
    return "custom"


@register("legalize_site")
def email_configuration_check(app_configs: Any = None, **kwargs: Any) -> list[Error | Warning]:
    """Validate the production email settings."""

    provider = None
    env_var = None
    mode = None

    messages: list[Error | Warning] = []

    if settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
        message_class = Error if getattr(settings, "IS_PRODUCTION", False) else Warning
        message_id = EMAIL_CONSOLE_ERROR_ID if getattr(settings, "IS_PRODUCTION", False) else EMAIL_CONSOLE_WARNING_ID
        messages.append(
            message_class(
                "EMAIL_BACKEND is set to the console backend, so messages are only printed to logs and never delivered.",
                hint=(
                    "Set SENDGRID_API_KEY, BREVO_API_KEY or SMTP credentials via environment variables to enable real email sending."
                ),
                id=message_id,
            )
        )

        default_from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "")
        if str(default_from_email).endswith("yourdomain.tld"):
            messages.append(
                Warning(
                    "DEFAULT_FROM_EMAIL still uses the placeholder domain 'yourdomain.tld'.",
                    hint=(
                        "Set DEFAULT_FROM_EMAIL (or REPLY_TO_EMAIL) to a provider-verified address via environment variables."
                    ),
                    id=EMAIL_WARNING_ID,
                )
            )

        return messages

    if settings.EMAIL_BACKEND in {
        "django.core.mail.backends.smtp.EmailBackend",
        "legalize_site.mail.SafeSMTPEmailBackend",
    }:
        provider = _smtp_provider()
        if provider == "Brevo":
            env_var = "BREVO_SMTP_PASSWORD"
        elif provider == "SendGrid":
            env_var = "SENDGRID_API_KEY"
        else:
            env_var = "EMAIL_HOST_PASSWORD"
        mode = "smtp"
    else:
        backend = BACKENDS.get(str(settings.EMAIL_BACKEND))
        if not backend:
            return []
        provider = backend["provider"]
        env_var = backend["env_var"]
        mode = backend["mode"]

    host_label = str(settings.EMAIL_HOST or "the SMTP host")
    provider_label = str(provider or "Email")
    if provider_label == "custom":
        provider_label = "SMTP"

    if mode == "api":
        api_key = getattr(settings, "ANYMAIL", {}).get(str(env_var)) or os.getenv(str(env_var))
        hint = f"Set the {env_var} environment variable so the anymail {provider_label} backend can authenticate against the provider API."
        provider_label = f"{provider_label} API key"
    else:
        api_key = getattr(settings, "EMAIL_HOST_PASSWORD", None) or os.getenv(str(env_var))
        hint = f"Set the {env_var} environment variable or provide a value for settings.EMAIL_HOST_PASSWORD so Django can authenticate with {host_label}."
        provider_label = f"{provider_label} SMTP password" if provider_label != "Email" else "SMTP password"

    if not api_key:
        messages.append(
            Error(
                f"{provider_label} is not configured.",
                hint=hint,
                id=EMAIL_ERROR_ID,
            )
        )

    default_from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "")
    if str(default_from_email).endswith("yourdomain.tld"):
        messages.append(
            Warning(
                "DEFAULT_FROM_EMAIL still uses the placeholder domain 'yourdomain.tld'.",
                hint=(
                    "Set DEFAULT_FROM_EMAIL (or REPLY_TO_EMAIL) to a provider-verified address via environment variables."
                ),
                id=EMAIL_WARNING_ID,
            )
        )

    return messages


@register("legalize_site")
def production_operations_check(app_configs: Any = None, **kwargs: Any) -> list[Error | Warning]:
    """Reject production configurations that cannot safely serve real clients."""

    if not getattr(settings, "IS_PRODUCTION", False):
        return []

    messages: list[Error | Warning] = []
    engine = str(getattr(settings, "DATABASES", {}).get("default", {}).get("ENGINE", ""))
    if engine != "django.db.backends.postgresql":
        messages.append(
            Error(
                "Production must use PostgreSQL; SQLite is not supported for live client data.",
                hint="Set DATABASE_URL (or Railway PostgreSQL variables) to a PostgreSQL database.",
                id=DATABASE_ENGINE_ERROR_ID,
            )
        )

    if getattr(settings, "CRON_FAILURE_EMAIL_ALERTS", False) and not getattr(settings, "ADMINS", ()):
        messages.append(
            Error(
                "Cron failure email alerts are enabled but ADMINS has no recipients.",
                hint="Set DJANGO_ADMIN_EMAILS to one or more monitored email addresses.",
                id=ALERT_RECIPIENTS_ERROR_ID,
            )
        )
    return messages


@register("legalize_site")
def encryption_configuration_check(app_configs: Any = None, **kwargs: Any) -> list[Error | Warning]:
    """Validate secret and encryption key configuration."""

    messages: list[Error | Warning] = []
    placeholder_secret = "django-insecure-change-me"  # nosec B105
    secret_key = getattr(settings, "SECRET_KEY", "")
    is_production = getattr(settings, "IS_PRODUCTION", False)
    fernet_configured = getattr(settings, "FERNET_KEYS_CONFIGURED", False)

    if is_production and (not secret_key or secret_key == placeholder_secret):
        messages.append(
            Error(
                "SECRET_KEY must be configured explicitly in production.",
                hint="Set a strong SECRET_KEY environment variable for the production deployment.",
                id=SECRET_KEY_ERROR_ID,
            )
        )
    elif not is_production and secret_key == placeholder_secret:
        messages.append(
            Warning(
                "SECRET_KEY is using the insecure default fallback value.",
                hint=(
                    "Set SECRET_KEY to a unique value for safer local development. In production this will be an error."
                ),
                id=SECRET_KEY_WARNING_ID,
            )
        )

    if is_production and not fernet_configured:
        messages.append(
            Error(
                "FERNET_KEYS must be configured explicitly in production.",
                hint=("Set FERNET_KEYS to one or more Fernet keys and do not rely on keys derived from SECRET_KEY."),
                id=FERNET_KEYS_ERROR_ID,
            )
        )
    elif not is_production and not fernet_configured:
        messages.append(
            Warning(
                "FERNET_KEYS environment variable is not set; encryption keys are derived from SECRET_KEY.",
                hint=(
                    "Set FERNET_KEYS to explicit Fernet keys for safer PII encryption. In production this will be an error."
                ),
                id=FERNET_KEYS_WARNING_ID,
            )
        )

    return messages


@register("legalize_site")
def runtime_dependency_check(app_configs: Any = None, **kwargs: Any) -> list[Error | Warning]:
    """Surface missing OCR/backup/runtime tooling as Django warnings."""

    messages: list[Error | Warning] = []
    for dependency in collect_runtime_dependency_statuses():
        if dependency["available"]:
            continue
        messages.append(
            Warning(
                f"{dependency['label']} is unavailable; {dependency['required_for']} will be degraded.",
                hint=dependency["hint"],
                id=RUNTIME_DEPENDENCY_WARNING_ID,
            )
        )
    return messages


@register("legalize_site")
def rate_limit_cache_check(app_configs: Any = None, **kwargs: Any) -> list[Error | Warning]:
    messages: list[Error | Warning] = []
    if not getattr(settings, "IS_PRODUCTION", False):
        return messages

    active_limits = [
        name for name, rule in getattr(settings, "RATE_LIMITS", {}).items() if int(rule.get("limit", 0)) > 0
    ]
    if not active_limits:
        return messages

    cache_backend = str(getattr(settings, "CACHES", {}).get("default", {}).get("BACKEND", ""))
    if cache_backend == "django.core.cache.backends.redis.RedisCache":
        return messages

    messages.append(
        Error(
            "Production rate limits need a shared cache backend.",
            hint=(
                "Set REDIS_URL for RedisCache. DatabaseCache increments are not atomic "
                "and cannot reliably enforce brute-force limits under concurrency."
            ),
            id=RATE_LIMIT_CACHE_ERROR_ID,
        )
    )
    return messages


MALWARE_SCAN_WARNING_ID = "legalize_site.W014"
STAFF_MFA_WARNING_ID = "legalize_site.W015"


@register("legalize_site")
def staff_mfa_check(app_configs: Any = None, **kwargs: Any) -> list[Error | Warning]:
    """Warn while active staff accounts can sign in without a second factor."""
    from django.db import OperationalError, ProgrammingError

    messages: list[Error | Warning] = []
    if not getattr(settings, "IS_PRODUCTION", False):
        return messages
    try:
        from allauth.mfa.models import Authenticator
        from django.contrib.auth import get_user_model

        staff = get_user_model().objects.filter(is_staff=True, is_active=True)
        unenrolled = staff.exclude(pk__in=Authenticator.objects.values_list("user_id", flat=True)).count()
    except (ImportError, OperationalError, ProgrammingError):
        # allauth.mfa disabled or tables not migrated yet (initial deploy).
        return messages
    if unenrolled:
        messages.append(
            Warning(
                f"{unenrolled} active staff account(s) have no two-factor authentication enrolled.",
                hint="Staff can enroll a TOTP app and recovery codes at /accounts/2fa/.",
                id=STAFF_MFA_WARNING_ID,
            )
        )
    return messages


@register("legalize_site")
def malware_scan_check(app_configs: Any = None, **kwargs: Any) -> list[Error | Warning]:
    """Warn while production accepts client uploads without malware scanning."""
    messages: list[Error | Warning] = []
    if not getattr(settings, "IS_PRODUCTION", False):
        return messages
    if getattr(settings, "MALWARE_SCAN_ENABLED", False):
        return messages
    messages.append(
        Warning(
            "Uploads are accepted without malware scanning.",
            hint=(
                "Run a clamd instance, point CLAMD_TCP_ADDR/CLAMD_TCP_PORT at it and "
                "set MALWARE_SCAN_ENABLED=True. Scanning is fail-closed once enabled."
            ),
            id=MALWARE_SCAN_WARNING_ID,
        )
    )
    return messages


@register("legalize_site")
def production_storage_safety_check(app_configs: Any = None, **kwargs: Any) -> list[Error | Warning]:
    messages: list[Error | Warning] = []
    is_production = getattr(settings, "IS_PRODUCTION", False)
    if not is_production:
        return messages

    use_s3 = getattr(settings, "USE_S3_MEDIA_STORAGE", False)
    use_database_media = getattr(settings, "USE_DATABASE_MEDIA_STORAGE", False)
    allow_local = os.environ.get("ALLOW_PRODUCTION_LOCAL_MEDIA", "").lower() in {"1", "true", "yes", "on"}
    if not use_s3 and not use_database_media and not allow_local:
        messages.append(
            Error(
                "Production media storage is not persistent.",
                hint=(
                    "Use S3/R2/B2 with USE_S3_MEDIA_STORAGE=True, PostgreSQL media storage "
                    "with USE_DATABASE_MEDIA_STORAGE=True, or mount a Railway Volume to MEDIA_ROOT "
                    "and set ALLOW_PRODUCTION_LOCAL_MEDIA=true."
                ),
                id=MEDIA_STORAGE_ERROR_ID,
            )
        )

    backup_remote = os.environ.get("BACKUP_REMOTE_STORAGE", "").lower() in {"1", "true", "yes", "on"}
    if not backup_remote:
        messages.append(
            Error(
                "Remote backup storage is not enabled in production.",
                hint="Enable BACKUP_REMOTE_STORAGE and configure remote object storage, or ensure persistent volume retention.",
                id=BACKUP_STORAGE_ERROR_ID,
            )
        )
    else:
        backup_alias = str(getattr(settings, "BACKUP_STORAGE_ALIAS", "backups"))
        storages_config = getattr(settings, "STORAGES", {})
        backup_config = storages_config.get(backup_alias, {})
        if not backup_config:
            messages.append(
                Error(
                    "Remote database backup storage is not explicitly configured.",
                    hint=(
                        f"Configure STORAGES[{backup_alias!r}] for backups; do not route database "
                        "backups through the database media storage backend."
                    ),
                    id=MEDIA_STORAGE_ERROR_ID,
                )
            )
        elif backup_config.get("BACKEND") == "database_media.storage.DatabaseMediaStorage":
            messages.append(
                Error(
                    "Database backups cannot use DatabaseMediaStorage.",
                    hint="Configure BACKUP_STORAGE_ALIAS to point at object storage or another storage outside the database.",
                    id=MEDIA_STORAGE_ERROR_ID,
                )
            )
        elif backup_config.get("BACKEND") == "storages.backends.s3.S3Storage":
            backup_options = backup_config.get("OPTIONS", {})
            if not backup_options.get("bucket_name"):
                messages.append(
                    Error(
                        "Remote database backup storage has no bucket configured.",
                        hint="Set AWS_STORAGE_BUCKET_NAME for S3/R2/B2 backup uploads.",
                        id=MEDIA_STORAGE_ERROR_ID,
                    )
                )

    return messages


@register("legalize_site")
def cron_allowed_ips_check(app_configs: Any = None, **kwargs: Any) -> list[Error | Warning]:
    messages: list[Error | Warning] = []
    is_production = getattr(settings, "IS_PRODUCTION", False)
    if not is_production:
        return messages

    cron_allowed_ips = os.environ.get("CRON_ALLOWED_IPS", "").strip()
    if not cron_allowed_ips:
        messages.append(
            Warning(
                "CRON_ALLOWED_IPS is empty in production.",
                hint="CRON_TOKEN provides baseline security, but configuring CRON_ALLOWED_IPS adds an important IP allowlist layer.",
                id="legalize_site.W009",
            )
        )
    return messages


@register("legalize_site")
def cron_token_check(app_configs: Any = None, **kwargs: Any) -> list[Error | Warning]:
    messages: list[Error | Warning] = []
    if not getattr(settings, "IS_PRODUCTION", False):
        return messages

    if not os.environ.get("CRON_TOKEN", "").strip():
        messages.append(
            Error(
                "CRON_TOKEN is not configured in production.",
                hint="Set CRON_TOKEN and pass it as Authorization: Bearer <token> or X-CRON-TOKEN for every cron request.",
                id=CRON_TOKEN_ERROR_ID,
            )
        )
    return messages


@register("legalize_site")
def translation_tooling_check(app_configs: Any = None, **kwargs: Any) -> list[Error | Warning]:
    messages: list[Error | Warning] = []
    if not getattr(settings, "IS_PRODUCTION", False):
        return messages

    if getattr(settings, "ENABLE_TRANSLATION_TOOLING", False):
        messages.append(
            Warning(
                "Translation tooling is enabled in production.",
                hint=(
                    "Set ENABLE_TRANSLATION_TOOLING=False unless the internal translation editor "
                    "is intentionally exposed to authenticated translator/admin roles."
                ),
                id=TRANSLATION_TOOLING_WARNING_ID,
            )
        )
    return messages


@register("legalize_site")
def upload_policy_check(app_configs: Any = None, **kwargs: Any) -> list[Error | Warning]:
    messages: list[Error | Warning] = []
    max_upload_mb = int(getattr(settings, "MAX_UPLOAD_SIZE_MB", 0) or 0)
    if max_upload_mb <= 0:
        messages.append(
            Error(
                "MAX_UPLOAD_SIZE_MB must be a positive integer.",
                hint="Set MAX_UPLOAD_SIZE_MB to a conservative value such as 20.",
                id=UPLOAD_LIMIT_ERROR_ID,
            )
        )

    from clients.validators import ALLOWED_DOCUMENTS

    if not ALLOWED_DOCUMENTS:
        messages.append(
            Error(
                "Allowed document upload types are empty.",
                hint="Configure clients.validators.ALLOWED_DOCUMENTS with explicit extensions and MIME types.",
                id=UPLOAD_TYPES_ERROR_ID,
            )
        )
    return messages


@register("database")
def check_database_schema(app_configs: Any = None, **kwargs: Any) -> list[Error | Warning]:
    """
    Validate that the database schema (tables and columns) matches the active Django models.
    This prevents running with missing database columns/tables after schema desync.
    """
    from django.apps import apps
    from django.db import OperationalError, ProgrammingError, connection

    messages: list[Error | Warning] = []

    # Skip check if we're running tests or if migrations are currently being executed,
    # as database structure checks are only relevant for a running application.
    if os.environ.get("DJANGO_SETTINGS_MODULE") == "legalize_site.settings.test":
        return messages

    try:
        # Test connection quickly
        with connection.cursor() as cursor:
            pass
    except (ProgrammingError, OperationalError):
        # Database not accessible or not initialized yet (e.g. during initial Docker build steps)
        return messages

    try:
        table_names = connection.introspection.table_names()

        for model in apps.get_models():
            # Only check managed models
            if not model._meta.managed:
                continue

            db_table = model._meta.db_table

            # 1. Check table existence
            if db_table not in table_names:
                messages.append(
                    Warning(
                        f"Database table '{db_table}' for model '{model.__name__}' does not exist in the database.",
                        hint="Run 'python manage.py migrate' to create the missing table.",
                        id="legalize_site.W012",
                    )
                )
                continue

            # 2. Check column existence
            with connection.cursor() as cursor:
                table_description = connection.introspection.get_table_description(cursor, db_table)
                actual_columns = {col.name for col in table_description}

            for field in model._meta.fields:
                if not field.concrete:
                    continue
                db_column = field.column
                if db_column not in actual_columns:
                    messages.append(
                        Warning(
                            f"Column '{db_column}' for field '{field.name}' in model '{model.__name__}' does not exist in table '{db_table}'.",
                            hint=f"Create and apply a new migration to add column '{db_column}' to table '{db_table}'.",
                            id="legalize_site.W013",
                        )
                    )
    except Exception as e:
        messages.append(
            Warning(
                f"Failed to inspect database schema for consistency check: {e}",
                hint="Verify database connectivity and permissions.",
                id="legalize_site.W014",
            )
        )

    return messages
