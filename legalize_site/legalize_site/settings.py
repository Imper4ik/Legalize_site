"""
Django settings for legalize_site project.
"""

from importlib.util import find_spec
from pathlib import Path
import os
import dj_database_url
from django.utils.translation import gettext_lazy as _

# ==== БАЗОВОЕ ====

BASE_DIR = Path(__file__).resolve().parent.parent

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
]

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
# Важно: LocaleMiddleware должен идти ПОСЛЕ SessionMiddleware и ДО CommonMiddleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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
# Если DATABASE_URL не задан — используем локальную SQLite.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=0,
    )
}

# ==== ПАРОЛИ ====
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ==== СТАТИКА / МЕДИА ====
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"   # для collectstatic в проде
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ==== ALLAUTH (современные опции) ====
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Используем вход только по email, username не обязателен
ACCOUNT_LOGIN_METHODS = {"email"}                   # замена устаревшему ACCOUNT_AUTHENTICATION_METHOD
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]  # замена устаревшим EMAIL_REQUIRED/USERNAME_REQUIRED
# НЕ задаём ACCOUNT_USER_MODEL_USERNAME_FIELD=None, т.к. стандартная модель User имеет username

# Верификация email: mandatory/optional/none
ACCOUNT_EMAIL_VERIFICATION = os.getenv("ACCOUNT_EMAIL_VERIFICATION", "mandatory")

LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "root_dashboard"
LOGOUT_REDIRECT_URL = "account_login"

SOCIALACCOUNT_AUTO_SIGNUP = True

# ==== ПОЧТА (Brevo SMTP) ====
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp-relay.brevo.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() in ("1", "true", "yes", "on")
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")              # ваш SMTP login из Brevo (без пробелов)
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")      # SMTP key из Brevo
_DEFAULT_SMTP_BACKEND = "legalize_site.mail.SafeSMTPEmailBackend"

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND")
if not EMAIL_BACKEND:
    if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
        EMAIL_BACKEND = _DEFAULT_SMTP_BACKEND
    else:
        # В режиме разработки (без настроенного SMTP) выводим письма в консоль,
        # чтобы формы сброса пароля не падали с 500 ошибкой.
        EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL") or EMAIL_HOST_USER or "webmaster@localhost"
SERVER_EMAIL = DEFAULT_FROM_EMAIL
