"""
Django settings for legalize_site project.
"""

from pathlib import Path
from importlib.util import find_spec
import os
from django.utils.translation import gettext_lazy as _
from dotenv import load_dotenv, find_dotenv
import dj_database_url

# ==== БАЗОВОЕ ====

BASE_DIR = Path(__file__).resolve().parent.parent

# Загружаем .env из ближайшего расположения и подстраховываемся путями проекта
load_dotenv(find_dotenv())
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
DEBUG = os.getenv("DEBUG", "0").lower() in ("1", "true", "yes", "on")
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Warsaw"
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("ru", _("Русский")),
    ("pl", _("Polski")),
    ("en", _("English")),
]
LOCALE_PATHS = [BASE_DIR / "locale"]

# ==== ПРИЛОЖЕНИЯ ====

INSTALLED_APPS = [
    # django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sites",

    # проект
    "clients",
    "portal",

    # allauth
    "allauth",
    "allauth.account",
    "allauth.socialaccount",

    # Почта через API (Anymail, Brevo) — держим в списке, чтобы можно было включить по ключу
    "anymail",
]

# Опционально добавим провайдера Google, если установлен requests (как в исходнике)
_SOCIALACCOUNT_PROVIDER_SETTINGS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
    }
}
if find_spec("requests") is not None:
    INSTALLED_APPS.append("allauth.socialaccount.providers.google")
    SOCIALACCOUNT_PROVIDERS = _SOCIALACCOUNT_PROVIDER_SETTINGS
else:
    SOCIALACCOUNT_PROVIDERS = {}

SITE_ID = int(os.getenv("SITE_ID", "1"))

# ==== MIDDLEWARE ====
# Важно: LocaleMiddleware — ПОСЛЕ SessionMiddleware и ДО CommonMiddleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise — если установлен, включим сразу после SecurityMiddleware
    *(
        ["whitenoise.middleware.WhiteNoiseMiddleware"]
        if find_spec("whitenoise") is not None
        else []
    ),
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "legalize_site.urls"

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
            ],
        },
    },
]

WSGI_APPLICATION = "legalize_site.wsgi.application"

# ==== БАЗА ДАННЫХ ====
# По умолчанию — SQLite; если есть DATABASE_URL — применяем его.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
_db_url = os.getenv("DATABASE_URL")
if _db_url:
    # Совместимо со старыми версиями dj-database-url
    try:
        DATABASES["default"] = dj_database_url.config(default=_db_url, conn_max_age=0)
    except TypeError:
        DATABASES["default"] = dj_database_url.parse(_db_url)

# ==== СТАТИКА / МЕДИА ====
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"   # для collectstatic в проде
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# WhiteNoise storage — если установлен whitenoise
if find_spec("whitenoise") is not None:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ==== ALLAUTH (современные опции) ====
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Современные ключи allauth
ACCOUNT_LOGIN_METHODS = {"email"}                   # вместо устаревшего ACCOUNT_AUTHENTICATION_METHOD
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]  # вместо старых *_REQUIRED
ACCOUNT_EMAIL_VERIFICATION = os.getenv("ACCOUNT_EMAIL_VERIFICATION", "mandatory")

LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "root_dashboard"
LOGOUT_REDIRECT_URL = "account_login"

SOCIALACCOUNT_AUTO_SIGNUP = True

# ==== ПОЧТА ====
# 1) Если задан BREVO_API_KEY → Anymail (Brevo API)
# 2) Иначе если заданы EMAIL_HOST_USER/EMAIL_HOST_PASSWORD → SMTP
# 3) Иначе — console backend для разработки
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp-relay.brevo.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() in ("1", "true", "yes", "on")
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")          # SMTP login (Brevo)
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")  # SMTP key (Brevo)

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND")  # можно принудительно переопределить через ENV
if not EMAIL_BACKEND:
    if BREVO_API_KEY:
        EMAIL_BACKEND = "anymail.backends.brevo.EmailBackend"
        ANYMAIL = {"BREVO_API_KEY": BREVO_API_KEY}
    elif EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
        EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    else:
        EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

DEFAULT_FROM_EMAIL = (
    os.getenv("DEFAULT_FROM_EMAIL")
    or EMAIL_HOST_USER
    or "noreply@localhost"
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Для корректного определения HTTPS за обратным прокси (например, Render)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
