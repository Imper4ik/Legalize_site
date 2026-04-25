"""Base settings shared across environments."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import os
import sys
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


load_env()

WHITENOISE_AVAILABLE = importlib.util.find_spec("whitenoise") is not None
STORAGES_AVAILABLE = importlib.util.find_spec("storages") is not None
DEFAULT_SECRET_KEY_FALLBACK = "django-insecure-change-me"


def running_in_production() -> bool:
    settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
    app_env = os.environ.get("APP_ENV", "")
    return settings_module.endswith(".production") or app_env.lower() == "production"


IS_PRODUCTION = running_in_production()
ENABLE_TRANSLATION_TOOLING = env_flag(
    "ENABLE_TRANSLATION_TOOLING",
    "True",
)
AUTO_COMPILE_TRANSLATIONS_ON_STARTUP = env_flag("AUTO_COMPILE_TRANSLATIONS_ON_STARTUP", "False")

# --- БАЗОВЫЕ НАСТРОЙКИ ---
SECRET_KEY = os.environ.get("SECRET_KEY", DEFAULT_SECRET_KEY_FALLBACK)
DEBUG = False


def _derive_fernet_key(secret: str) -> str:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")


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
        "email",
        "phone",
        "passport",
        "case_number",
        "case-number",
        "raw_text",
        "ocr",
        "fingerprint",
        "decision_date",
        "full_name",
        "first_name",
        "last_name",
        "authorization",
        "token",
        "secret",
        "password",
        "api_key",
        "api-key",
    )
    return any(fragment in normalized for fragment in sensitive_fragments)


def _sanitize_sentry_value(value, *, key_hint: str | None = None):
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


def _sentry_before_send(event, hint):
    event = dict(event)
    if "request" in event:
        request_data = dict(event["request"])
        request_data.pop("cookies", None)
        if request_data.get("method", "").upper() == "POST":
            request_data["data"] = REDACTION_TOKEN
        else:
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
    return event


def _sentry_before_breadcrumb(crumb, hint):
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
    "users.apps.UsersConfig",
    "clients.apps.ClientsConfig",
    "submissions.apps.SubmissionsConfig",
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
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "legalize_site.security.RateLimitMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")
USE_S3_MEDIA_STORAGE = env_flag("USE_S3_MEDIA_STORAGE", "False")
PRIVATE_MEDIA_LOCATION = os.environ.get("PRIVATE_MEDIA_LOCATION", "private")
if USE_S3_MEDIA_STORAGE and not STORAGES_AVAILABLE:
    raise ImproperlyConfigured("USE_S3_MEDIA_STORAGE requires django-storages to be installed.")
if USE_S3_MEDIA_STORAGE:
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
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": AWS_STORAGE_BUCKET_NAME,
                "region_name": AWS_S3_REGION_NAME or None,
                "endpoint_url": AWS_S3_ENDPOINT_URL or None,
                "custom_domain": AWS_S3_CUSTOM_DOMAIN or None,
                "default_acl": None,
                "querystring_auth": True,
                "file_overwrite": False,
                "location": PRIVATE_MEDIA_LOCATION,
            },
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if WHITENOISE_AVAILABLE
            else "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

# --- ШРИФТ ДЛЯ PDF-ОТЧЕТОВ ---
PDF_FONT_PATH = os.getenv("PDF_FONT_PATH", "")

# --- ДОПУСТИМЫЙ РАЗМЕР ЗАГРУЗОК ---
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "20"))
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE
MAX_IMAGE_PIXELS = int(os.environ.get("MAX_IMAGE_PIXELS", "25000000"))
MAX_UPLOAD_FILENAME_LENGTH = int(os.environ.get("MAX_UPLOAD_FILENAME_LENGTH", "180"))

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
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_AUTHENTICATION_METHOD = "email"
ACCOUNT_ADAPTER = "users.adapters.InternalAccountAdapter"
SOCIALACCOUNT_ADAPTER = "users.adapters.InternalSocialAccountAdapter"

# Новые ключи (вместо устаревших ACCOUNT_AUTHENTICATION_METHOD / ACCOUNT_USERNAME_REQUIRED)
ACCOUNT_LOGIN_METHODS = {"email"}  # логин только по email
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]  # поля регистрации

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
        "message": _("Too many login attempts. Try again later."),
    },
    "account_resend_verification": {
        "limit": int(os.environ.get("RATE_LIMIT_RESEND_VERIFICATION", "3")),
        "window_seconds": int(os.environ.get("RATE_LIMIT_RESEND_VERIFICATION_WINDOW", "600")),
        "by_user": False,
        "by_ip": True,
        "message": _("Too many verification email requests. Try again later."),
    },
    "clients:add_document": {
        "limit": int(os.environ.get("RATE_LIMIT_DOCUMENT_UPLOAD", "20")),
        "window_seconds": int(os.environ.get("RATE_LIMIT_DOCUMENT_UPLOAD_WINDOW", "3600")),
        "message": _("Too many document uploads. Try again later."),
    },
    "clients:mass_email": {
        "limit": int(os.environ.get("RATE_LIMIT_MASS_EMAIL", "3")),
        "window_seconds": int(os.environ.get("RATE_LIMIT_MASS_EMAIL_WINDOW", "3600")),
        "message": _("Too many bulk email actions. Try again later."),
    },
    "clients:run_update_reminders": {
        "limit": int(os.environ.get("RATE_LIMIT_REMINDER_RUN", "5")),
        "window_seconds": int(os.environ.get("RATE_LIMIT_REMINDER_RUN_WINDOW", "3600")),
        "message": _("Too many reminder refresh requests. Try again later."),
    },
    "clients:send_custom_email": {
        "limit": int(os.environ.get("RATE_LIMIT_SEND_CUSTOM_EMAIL", "20")),
        "window_seconds": int(os.environ.get("RATE_LIMIT_SEND_CUSTOM_EMAIL_WINDOW", "3600")),
        "message": _("Too many email sends. Try again later."),
    },
}

# --- SENTRY ---
SENTRY_DSN = os.environ.get("SENTRY_DSN")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=1.0,
        send_default_pii=False,
        max_request_body_size="never",
        before_send=_sentry_before_send,
        before_breadcrumb=_sentry_before_breadcrumb,
    )
