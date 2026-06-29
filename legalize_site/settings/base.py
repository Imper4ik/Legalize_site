"""Base settings shared across environments."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import os
import sys
from typing import Any
from urllib.parse import quote_plus

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from ..env import BASE_DIR, load_env
from ..utils.logging import REDACTION_TOKEN, redact_text


def env_flag(name: str, default: str = "False") -> bool:
    """Return environment variable value as a boolean flag.

    Treats common truthy strings ("1", "true", "yes", "on") as ``True`` and
    everything else as ``False``. Providing a default keeps local development and
    test environments predictable when the variable is absent.
    """

    return os.environ.get(name, default).lower() in ("1", "true", "yes", "on")


def env_float(name: str, default: str) -> float:
    """Return an environment variable value as a float."""

    try:
        return float(os.environ.get(name, default))
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be a valid float.") from exc


load_env()

WHITENOISE_AVAILABLE = importlib.util.find_spec("whitenoise") is not None
STORAGES_AVAILABLE = importlib.util.find_spec("storages") is not None
DJANGO_CLEANUP_AVAILABLE = importlib.util.find_spec("django_cleanup") is not None
DEFAULT_SECRET_KEY_FALLBACK = "django-insecure-change-me"  # nosec B105


def running_in_production() -> bool:
    settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
    app_env = os.environ.get("APP_ENV", "")
    return settings_module.endswith(".production") or app_env.lower() == "production"


IS_PRODUCTION = running_in_production()
ENABLE_TRANSLATION_TOOLING = env_flag(
    "ENABLE_TRANSLATION_TOOLING",
    "True",
)
TRANSLATION_STUDIO_STORAGE = os.environ.get("TRANSLATION_STUDIO_STORAGE", "database")
TRANSLATION_DB_OVERRIDES_ENABLED = env_flag("TRANSLATION_DB_OVERRIDES_ENABLED", "True")
AUTO_COMPILE_TRANSLATIONS_ON_STARTUP = env_flag("AUTO_COMPILE_TRANSLATIONS_ON_STARTUP", "False")
ASYNC_OCR_PROCESSING = env_flag("ASYNC_OCR_PROCESSING", "False")
ENABLE_TEST_CENTER = env_flag("ENABLE_TEST_CENTER", "True")
TEST_CENTER_MEDIA_ROOT = os.environ.get("TEST_CENTER_MEDIA_ROOT", "")
DEMO_MODE_ENABLED = env_flag("DEMO_MODE_ENABLED", "True")
DEMO_CENTER_MEDIA_ROOT = os.environ.get("DEMO_CENTER_MEDIA_ROOT", "")

# --- БАЗОВЫЕ НАСТРОЙКИ ---
SECRET_KEY = os.environ.get("SECRET_KEY", DEFAULT_SECRET_KEY_FALLBACK)
DEBUG = False
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


def _derive_fernet_key(secret: str) -> str:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")


if os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith(".test") and not os.environ.get("FERNET_KEYS"):
    os.environ["FERNET_KEYS"] = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="

FERNET_KEYS = [key.strip() for key in os.environ.get("FERNET_KEYS", "").split(",") if key.strip()]
FERNET_KEYS_CONFIGURED = bool(FERNET_KEYS)

IS_BUILD_PHASE = len(sys.argv) > 1 and sys.argv[1] in ("collectstatic", "compilemessages", "makemessages")

if IS_PRODUCTION and not IS_BUILD_PHASE and (not SECRET_KEY or SECRET_KEY == DEFAULT_SECRET_KEY_FALLBACK):
    raise ImproperlyConfigured("SECRET_KEY must be set explicitly in production.")
if IS_PRODUCTION and not IS_BUILD_PHASE and not FERNET_KEYS_CONFIGURED:
    raise ImproperlyConfigured("FERNET_KEYS must be set explicitly in production.")
if not FERNET_KEYS:
    FERNET_KEYS = [_derive_fernet_key(SECRET_KEY)]


def _is_sensitive_key(key: str | None) -> bool:
    if not key:
        return False
    normalized = key.lower()
    sensitive_fragments = (
        "address",
        "authorization",
        "case_number",
        "case-number",
        "client",
        "decision_date",
        "document",
        "email",
        "fingerprint",
        "first_name",
        "full_name",
        "key",
        "last_name",
        "ocr",
        "passport",
        "passport_num",
        "passport_number",
        "password",
        "pesel",
        "phone",
        "raw_text",
        "secret",
        "token",
    )
    return any(fragment in normalized for fragment in sensitive_fragments)


def _sanitize_sentry_value(value: Any, *, key_hint: str | None = None) -> Any:
    if value is None:
        return None
    if _is_sensitive_key(key_hint):
        return REDACTION_TOKEN
    if isinstance(value, dict):
        return {
            key: _sanitize_sentry_value(item, key_hint=str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_sentry_value(item, key_hint=key_hint) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_sentry_value(item, key_hint=key_hint) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value


def _sanitize_sentry_exception(exception: Any) -> Any:
    if not isinstance(exception, dict):
        return exception
    exception_data = dict(exception)
    values = exception_data.get("values")
    if not isinstance(values, list):
        return exception_data

    sanitized_values = []
    for exception_value in values:
        if not isinstance(exception_value, dict):
            sanitized_values.append(exception_value)
            continue

        exception_value_data = dict(exception_value)
        stacktrace = exception_value_data.get("stacktrace")
        if isinstance(stacktrace, dict):
            stacktrace_data = dict(stacktrace)
            frames = stacktrace_data.get("frames")
            if isinstance(frames, list):
                sanitized_frames = []
                for frame in frames:
                    if not isinstance(frame, dict):
                        sanitized_frames.append(frame)
                        continue
                    frame_data = dict(frame)
                    if "vars" in frame_data:
                        frame_data["vars"] = _sanitize_sentry_value(frame_data.get("vars"))
                    sanitized_frames.append(frame_data)
                stacktrace_data["frames"] = sanitized_frames
            exception_value_data["stacktrace"] = stacktrace_data
        sanitized_values.append(exception_value_data)

    exception_data["values"] = sanitized_values
    return exception_data


def _sentry_before_send(event: Any, hint: Any) -> Any:
    event = dict(event)
    if "request" in event:
        request_data = dict(event["request"])
        request_data.pop("cookies", None)
        request_data["data"] = _sanitize_sentry_value(request_data.get("data"))
        request_data["headers"] = _sanitize_sentry_value(request_data.get("headers"))
        request_data["query_string"] = _sanitize_sentry_value(request_data.get("query_string"))
        request_data["env"] = _sanitize_sentry_value(request_data.get("env"))
        request_data["url"] = _sanitize_sentry_value(request_data.get("url"))
        event["request"] = request_data
    if "user" in event:
        event["user"] = _sanitize_sentry_value(event["user"])
    if "extra" in event:
        event["extra"] = _sanitize_sentry_value(event["extra"])
    if "contexts" in event:
        event["contexts"] = _sanitize_sentry_value(event["contexts"])
    if "breadcrumbs" in event:
        event["breadcrumbs"] = _sanitize_sentry_value(event["breadcrumbs"])
    if "exception" in event:
        event["exception"] = _sanitize_sentry_exception(event["exception"])
    return event


def _sentry_before_breadcrumb(crumb: Any, hint: Any) -> Any:
    return _sanitize_sentry_value(crumb)

# --- ПРИЛОЖЕНИЯ И MIDDLEWARE ---
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sites",
    "database_media.apps.DatabaseMediaConfig",
    "users.apps.UsersConfig",
    "clients.apps.ClientsConfig",
    "submissions.apps.SubmissionsConfig",
    "legalize_site",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "anymail",
]
if ENABLE_TRANSLATION_TOOLING:
    INSTALLED_APPS.extend(
        [
            "rosetta",
            "translations",
        ]
    )
if DJANGO_CLEANUP_AVAILABLE:
    INSTALLED_APPS.append("django_cleanup.apps.CleanupConfig")

AUTH_USER_MODEL = "users.User"

# --- ROSETTA ---
ROSETTA_SHOW_AT_ADMIN_PANEL = ENABLE_TRANSLATION_TOOLING
ROSETTA_EXCLUDED_APPLICATIONS = (
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "allauth",
)

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

if WHITENOISE_AVAILABLE:
    INSTALLED_APPS.insert(
        INSTALLED_APPS.index("django.contrib.staticfiles"),
        "whitenoise.runserver_nostatic",
    )

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
]
if WHITENOISE_AVAILABLE:
    MIDDLEWARE.append("whitenoise.middleware.WhiteNoiseMiddleware")
MIDDLEWARE += [
    "legalize_site.observability.RequestIDMiddleware",
    "clients.middleware.OnboardingLinkExpiredMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "legalize_site.security.RateLimitMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "legalize_site.security.PermissionsPolicyMiddleware",
    "legalize_site.security.ContentSecurityPolicyMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]
if ENABLE_TRANSLATION_TOOLING:
    MIDDLEWARE.insert(
        MIDDLEWARE.index("allauth.account.middleware.AccountMiddleware"),
        "translations.middleware.TranslationStudioMiddleware",
    )

ROOT_URLCONF = "legalize_site.urls"
WSGI_APPLICATION = "legalize_site.wsgi.application"
ASGI_APPLICATION = "legalize_site.asgi.application"
CSRF_FAILURE_VIEW = "legalize_site.views.csrf_failure"

# --- ШАБЛОНЫ ---
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "legalize_site.context_processors.feature_flags",
                "legalize_site.context_processors.onboarding_notifications",
                "legalize_site.context_processors.onboarding_progress",
                "legalize_site.context_processors.prefilled_email",
            ],
            "libraries": {
                "form_filters": "clients.templatetags.form_filters",
            },
            "builtins": ["legalize_site.templatetags.i18n_compat"],
        },
    },
]

# --- БАЗА ДАННЫХ (НАСТРОЕНО ДЛЯ RAILWAY/RENDER) ---
DEFAULT_DATABASE_URL = f"sqlite:///{BASE_DIR / 'db.sqlite3'}"


def preferred_database_url() -> str:
    """Prefer Railway-provisioned PostgreSQL credentials when present."""

    for env_name in ("DATABASE_URL", "RAILWAY_DATABASE_URL"):
        url = os.environ.get(env_name)
        if url:
            return url

    pg_user = os.environ.get("PGUSER") or os.environ.get("POSTGRES_USER")
    pg_password = os.environ.get("PGPASSWORD") or os.environ.get("POSTGRES_PASSWORD")
    pg_host = os.environ.get("PGHOST") or os.environ.get("POSTGRES_HOST")
    pg_port = os.environ.get("PGPORT") or os.environ.get("POSTGRES_PORT") or "5432"
    pg_db = os.environ.get("PGDATABASE") or os.environ.get("POSTGRES_DB")

    if pg_user and pg_host and pg_db:
        password_part = f":{quote_plus(pg_password)}" if pg_password else ""
        return f"postgresql://{pg_user}{password_part}@{pg_host}:{pg_port}/{pg_db}"

    return DEFAULT_DATABASE_URL


DATABASES = {
    "default": dj_database_url.config(default=preferred_database_url()),
}

# dj_database_url returns an empty dict if DATABASE_URL is set but blank; guard
# against that so Django always receives a valid ENGINE configuration.
if not DATABASES["default"].get("ENGINE"):
    DATABASES["default"] = dj_database_url.parse(DEFAULT_DATABASE_URL)

# Persistent connections: avoid per-request connect/disconnect overhead in
# production with gunicorn workers.  CONN_HEALTH_CHECKS lets Django silently
# reconnect when a pooled connection goes stale.
DATABASES["default"]["CONN_MAX_AGE"] = int(os.environ.get("CONN_MAX_AGE", "600"))
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# Limit staff sessions to 8 hours (one work day) by default.
SESSION_COOKIE_AGE = int(os.environ.get("SESSION_COOKIE_AGE", "28800"))

# --- ВАЛИДАТОРЫ ПАРОЛЕЙ ---
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- ИНТЕРНАЦИОНАЛИЗАЦИЯ ---
LANGUAGES = [
    ("ru", _("Русский")),
    ("pl", _("Polski")),
    ("en", _("English")),
]
LOCALE_PATHS = [os.path.join(BASE_DIR, "locale")]
LANGUAGE_CODE = "pl"
TIME_ZONE = "Europe/Warsaw"
USE_I18N = True
USE_TZ = True

# --- СТАТИКА И МЕДИА (WHITENOISE) ---
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
if WHITENOISE_AVAILABLE:
    STORAGES: dict[str, dict[str, Any]] = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }

MEDIA_URL = "/media/"
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", str(BASE_DIR / "media"))
DATABASE_MEDIA_TEMP_ROOT = os.environ.get("DATABASE_MEDIA_TEMP_ROOT", str(BASE_DIR / "tmp" / "database_media"))
USE_DATABASE_MEDIA_STORAGE = env_flag("USE_DATABASE_MEDIA_STORAGE", "False")
DATABASE_MEDIA_FALLBACK_TO_FILE_SYSTEM = env_flag("DATABASE_MEDIA_FALLBACK_TO_FILE_SYSTEM", "True")
DATABASE_MEDIA_AUTO_IMPORT_LEGACY_FILES = env_flag("DATABASE_MEDIA_AUTO_IMPORT_LEGACY_FILES", "True")
DATABASE_MEDIA_TEMP_MAX_AGE_HOURS = int(os.environ.get("DATABASE_MEDIA_TEMP_MAX_AGE_HOURS", "24"))
USE_S3_MEDIA_STORAGE = env_flag("USE_S3_MEDIA_STORAGE", "False")
PRIVATE_MEDIA_LOCATION = os.environ.get("PRIVATE_MEDIA_LOCATION", "private")
BACKUP_STORAGE_ALIAS = os.environ.get("BACKUP_STORAGE_ALIAS", "backups")
BACKUP_STORAGE_LOCATION = os.environ.get("BACKUP_STORAGE_LOCATION", "db_backups")
BACKUP_REMOTE_STORAGE = env_flag("BACKUP_REMOTE_STORAGE", "False")
AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME", "")
AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "")
AWS_S3_ENDPOINT_URL = os.environ.get("AWS_S3_ENDPOINT_URL", "")
AWS_S3_CUSTOM_DOMAIN = os.environ.get("AWS_S3_CUSTOM_DOMAIN", "")
AWS_S3_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_S3_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
AWS_QUERYSTRING_AUTH = True
AWS_DEFAULT_ACL = None
AWS_S3_FILE_OVERWRITE = False
AWS_LOCATION = PRIVATE_MEDIA_LOCATION
if USE_DATABASE_MEDIA_STORAGE and USE_S3_MEDIA_STORAGE:
    raise ImproperlyConfigured("USE_DATABASE_MEDIA_STORAGE and USE_S3_MEDIA_STORAGE cannot both be enabled.")
if (USE_S3_MEDIA_STORAGE or BACKUP_REMOTE_STORAGE) and not STORAGES_AVAILABLE:
    raise ImproperlyConfigured("S3 media or backup storage requires django-storages to be installed.")


def _s3_storage_options(location: str) -> dict[str, Any]:
    return {
        "bucket_name": AWS_STORAGE_BUCKET_NAME,
        "region_name": AWS_S3_REGION_NAME or None,
        "endpoint_url": AWS_S3_ENDPOINT_URL or None,
        "custom_domain": AWS_S3_CUSTOM_DOMAIN or None,
        "default_acl": None,
        "querystring_auth": True,
        "file_overwrite": False,
        "location": location,
    }

if USE_DATABASE_MEDIA_STORAGE:
    STORAGES = {
        "default": {
            "BACKEND": "database_media.storage.DatabaseMediaStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if WHITENOISE_AVAILABLE
            else "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    if BACKUP_REMOTE_STORAGE:
        STORAGES[BACKUP_STORAGE_ALIAS] = {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": _s3_storage_options(BACKUP_STORAGE_LOCATION),
        }
elif USE_S3_MEDIA_STORAGE:
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": _s3_storage_options(PRIVATE_MEDIA_LOCATION),
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if WHITENOISE_AVAILABLE
            else "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
        BACKUP_STORAGE_ALIAS: {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": _s3_storage_options(BACKUP_STORAGE_LOCATION),
        },
    }

# --- ШРИФТ ДЛЯ PDF-ОТЧЕТОВ ---
PDF_FONT_PATH = os.getenv("PDF_FONT_PATH", "")

# --- ДОПУСТИМЫЙ РАЗМЕР ЗАГРУЗОК ---
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "20"))
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE
MAX_IMAGE_PIXELS = int(os.environ.get("MAX_IMAGE_PIXELS", "300000000"))
MAX_UPLOAD_FILENAME_LENGTH = int(os.environ.get("MAX_UPLOAD_FILENAME_LENGTH", "180"))
MAX_TOTAL_CLIENT_EXPORT_MB = int(os.environ.get("MAX_TOTAL_CLIENT_EXPORT_MB", "200"))

# --- ПОЧТА (SendGrid или Brevo через API или SMTP) ---
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
BREVO_SMTP_PASSWORD = os.getenv("BREVO_SMTP_PASSWORD")
BREVO_SMTP_USER = os.getenv("BREVO_SMTP_USER", "apikey")
BREVO_SMTP_HOST = os.getenv("BREVO_SMTP_HOST", "smtp-relay.brevo.com")
EMAIL_LOG_BODY_RETENTION_DAYS = int(os.environ.get("EMAIL_LOG_BODY_RETENTION_DAYS", "180"))

EMAIL_FALLBACK_TO_CONSOLE = env_flag(
    "EMAIL_FALLBACK_TO_CONSOLE",
    "True" if os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith(".development") else "False",
)

# Позволяет переопределить бэкенд явно через переменную окружения.
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND")

# Настройки SMTP (используются, когда выбран SMTP-бэкенд или заданы учётные данные).
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() in ("1", "true", "yes", "on")
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD") or SENDGRID_API_KEY

if not EMAIL_BACKEND:
    if BREVO_SMTP_PASSWORD:
        EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
        EMAIL_HOST = EMAIL_HOST or BREVO_SMTP_HOST
        EMAIL_HOST_USER = EMAIL_HOST_USER or BREVO_SMTP_USER
        EMAIL_HOST_PASSWORD = EMAIL_HOST_PASSWORD or BREVO_SMTP_PASSWORD
    elif SENDGRID_API_KEY:
        EMAIL_BACKEND = "anymail.backends.sendgrid.EmailBackend"
    elif BREVO_API_KEY:
        EMAIL_BACKEND = "anymail.backends.brevo.EmailBackend"
    elif EMAIL_HOST_PASSWORD:
        EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    else:
        EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

if EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend":
    if not EMAIL_HOST:
        EMAIL_HOST = BREVO_SMTP_HOST if BREVO_SMTP_PASSWORD else "smtp.sendgrid.net"
    EMAIL_HOST_USER = EMAIL_HOST_USER or (BREVO_SMTP_USER if "brevo" in EMAIL_HOST else "apikey")
    # Wrap SMTP so development can opt into console fallback without hiding
    # production delivery failures.
    EMAIL_BACKEND = "legalize_site.mail.SafeSMTPEmailBackend"

ANYMAIL = {}
if EMAIL_BACKEND == "anymail.backends.sendgrid.EmailBackend" and SENDGRID_API_KEY:
    ANYMAIL["SENDGRID_API_KEY"] = SENDGRID_API_KEY
if EMAIL_BACKEND == "anymail.backends.brevo.EmailBackend" and BREVO_API_KEY:
    ANYMAIL["BREVO_API_KEY"] = BREVO_API_KEY

# Обязательно укажи доменный адрес, подтверждённый в SendGrid (Domain Auth или Single Sender)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@legalize.pl")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Куда уйдёт ответ на письмо
EMAIL_REPLY_TO = os.getenv("REPLY_TO_EMAIL", "support@legalize.pl")

# --- DJANGO-ALLAUTH ---
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
SITE_ID = 1

ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_ADAPTER = "users.adapters.InternalAccountAdapter"
SOCIALACCOUNT_ADAPTER = "users.adapters.InternalSocialAccountAdapter"

# Email-only authentication settings for django-allauth 65+.
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]

# Редиректы
ACCOUNT_ALLOW_SIGNUPS = False

LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = reverse_lazy("clients:client_list")
LOGOUT_REDIRECT_URL = reverse_lazy("account_login")

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "redact_pii": {
            "()": "legalize_site.utils.logging.RedactPIIFilter",
        },
        "request_context": {
            "()": "legalize_site.utils.logging.RequestContextFilter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_context", "redact_pii"],
            "formatter": "structured",
        },
    },
    "formatters": {
        "structured": {
            "format": "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s correlation_id=%(correlation_id)s %(message)s",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
}

# Соц. вход через Google (по желанию)
SOCIALACCOUNT_AUTO_SIGNUP = False
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
    }
}

RATE_LIMITS = {
    "account_login": {
        "limit": int(os.environ.get("RATE_LIMIT_LOGIN", "5")),
        "window_seconds": int(os.environ.get("RATE_LIMIT_LOGIN_WINDOW", "300")),
        "by_user": False,
        "by_ip": True,
        "fail_closed": True,
        "message": _("Too many login attempts. Try again later."),
    },
    "account_resend_verification": {
        "limit": int(os.environ.get("RATE_LIMIT_RESEND_VERIFICATION", "3")),
        "window_seconds": int(os.environ.get("RATE_LIMIT_RESEND_VERIFICATION_WINDOW", "600")),
        "by_user": False,
        "by_ip": True,
        "fail_closed": True,
        "message": _("Too many verification email requests. Try again later."),
    },
    "clients:add_document": {
        "limit": int(os.environ.get("RATE_LIMIT_DOCUMENT_UPLOAD", "80")),
        "window_seconds": int(os.environ.get("RATE_LIMIT_DOCUMENT_UPLOAD_WINDOW", "3600")),
        "message": _("Too many document uploads. Try again later."),
    },
    "clients:mass_email": {
        "limit": int(os.environ.get("RATE_LIMIT_MASS_EMAIL", "3")),
        "window_seconds": int(os.environ.get("RATE_LIMIT_MASS_EMAIL_WINDOW", "3600")),
        "message": _("Too many bulk email actions. Try again later."),
    },
    "clients:run_update_reminders": {
        "limit": int(os.environ.get("RATE_LIMIT_REMINDER_RUN", "100")),
        "window_seconds": int(os.environ.get("RATE_LIMIT_REMINDER_RUN_WINDOW", "3600")),
        "message": _("Too many reminder refresh requests. Try again later."),
    },
    "clients:send_custom_email": {
        "limit": int(os.environ.get("RATE_LIMIT_SEND_CUSTOM_EMAIL", "20")),
        "window_seconds": int(os.environ.get("RATE_LIMIT_SEND_CUSTOM_EMAIL_WINDOW", "3600")),
        "message": _("Too many email sends. Try again later."),
    },
    "clients:onboarding_set_password": {
        "limit": int(os.environ.get("RATE_LIMIT_SET_PASSWORD", "5")),
        "window_seconds": int(os.environ.get("RATE_LIMIT_SET_PASSWORD_WINDOW", "300")),
        "by_user": False,
        "by_ip": True,
        "fail_closed": True,
        "message": _("Too many account creation attempts. Try again later."),
    },
    "clients:create_public_intake_link": {
        "limit": int(os.environ.get("RATE_LIMIT_CREATE_PUBLIC_INTAKE_LINK", "60")),
        "window_seconds": int(os.environ.get("RATE_LIMIT_CREATE_PUBLIC_INTAKE_LINK_WINDOW", "3600")),
        "message": _("Too many intake link requests. Try again later."),
    },
    "clients:public_intake": {
        "limit": int(os.environ.get("RATE_LIMIT_PUBLIC_INTAKE", "20")),
        "window_seconds": int(os.environ.get("RATE_LIMIT_PUBLIC_INTAKE_WINDOW", "3600")),
        "by_user": False,
        "by_ip": True,
        "fail_closed": True,
        "message": _("Too many intake submissions. Try again later."),
    },
}
RATE_LIMIT_CACHE_FAILURE_MODE = os.environ.get(
    "RATE_LIMIT_CACHE_FAILURE_MODE",
    "open",
).lower()
CRON_FAILURE_EMAIL_ALERTS = env_flag("CRON_FAILURE_EMAIL_ALERTS", "True" if IS_PRODUCTION else "False")

# --- SENTRY ---
SENTRY_DSN = os.environ.get("SENTRY_DSN")
SENTRY_ENVIRONMENT = (
    os.environ.get("SENTRY_ENVIRONMENT")
    or os.environ.get("RAILWAY_ENVIRONMENT")
    or ("production" if IS_PRODUCTION else None)
)
SENTRY_TRACES_SAMPLE_RATE = env_float(
    "SENTRY_TRACES_SAMPLE_RATE",
    "0.1" if IS_PRODUCTION else "1.0",
)
SENTRY_PROFILES_SAMPLE_RATE = env_float("SENTRY_PROFILES_SAMPLE_RATE", "0.0")
if not 0 <= SENTRY_TRACES_SAMPLE_RATE <= 1:
    raise ImproperlyConfigured("SENTRY_TRACES_SAMPLE_RATE must be between 0 and 1.")
if not 0 <= SENTRY_PROFILES_SAMPLE_RATE <= 1:
    raise ImproperlyConfigured("SENTRY_PROFILES_SAMPLE_RATE must be between 0 and 1.")

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=SENTRY_PROFILES_SAMPLE_RATE,
        environment=SENTRY_ENVIRONMENT,
        send_default_pii=False,
        max_request_body_size="never",
        before_send=_sentry_before_send,
        before_breadcrumb=_sentry_before_breadcrumb,
    )
