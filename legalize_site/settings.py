# legalize_site/settings.py

import importlib.util
import os
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import dj_database_url
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from .env import BASE_DIR, load_env


def env_flag(name: str, default: str = 'False') -> bool:
    """Return environment variable value as a boolean flag.

    Treats common truthy strings ("1", "true", "yes", "on") as ``True`` and
    everything else as ``False``. Providing a default keeps local development and
    test environments predictable when the variable is absent.
    """

    return os.environ.get(name, default).lower() in ("1", "true", "yes", "on")


load_env()

WHITENOISE_AVAILABLE = importlib.util.find_spec('whitenoise') is not None

# --- БАЗОВЫЕ НАСТРОЙКИ ---
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-change-me')
DEBUG = env_flag('DEBUG', 'True')

ALLOWED_HOSTS = [host for host in os.environ.get('ALLOWED_HOSTS', '').split(',') if host]
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
ALLOWED_HOSTS.extend(['127.0.0.1', 'localhost'])

CSRF_TRUSTED_ORIGINS = [origin for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if origin]
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

RAILWAY_STATIC_URL = os.environ.get('RAILWAY_STATIC_URL')
if RAILWAY_STATIC_URL:
    parsed = urlparse(RAILWAY_STATIC_URL)
    if parsed.hostname:
        ALLOWED_HOSTS.append(parsed.hostname)
        scheme = parsed.scheme or 'https'
        CSRF_TRUSTED_ORIGINS.append(f"{scheme}://{parsed.hostname}")

RAILWAY_PUBLIC_DOMAIN = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
if RAILWAY_PUBLIC_DOMAIN:
    hostname = RAILWAY_PUBLIC_DOMAIN.replace('https://', '').replace('http://', '')
    if hostname:
        ALLOWED_HOSTS.append(hostname)
        CSRF_TRUSTED_ORIGINS.append(f"https://{hostname}")

# За прокси (Render) — чтобы Django корректно видел HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = env_flag('SECURE_SSL_REDIRECT', 'False')
if SECURE_SSL_REDIRECT:
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '3600'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = os.environ.get('SECURE_HSTS_PRELOAD', 'True').lower() in ('1', 'true', 'yes', 'on')

# --- ПРИЛОЖЕНИЯ И MIDDLEWARE ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'django.contrib.humanize',
    'django.contrib.sites',

    'clients.apps.ClientsConfig',
    'submissions.apps.SubmissionsConfig',

    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'anymail',
]

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

if WHITENOISE_AVAILABLE:
    INSTALLED_APPS.insert(
        INSTALLED_APPS.index('django.contrib.staticfiles'),
        'whitenoise.runserver_nostatic'
    )

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
]
if WHITENOISE_AVAILABLE:
    MIDDLEWARE.append('whitenoise.middleware.WhiteNoiseMiddleware')
MIDDLEWARE += [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'legalize_site.urls'
WSGI_APPLICATION = 'legalize_site.wsgi.application'

# --- ШАБЛОНЫ ---
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
            'libraries': {
                'form_filters': 'clients.templatetags.form_filters',
            },
            'builtins': ['legalize_site.templatetags.i18n_compat'],
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
    'default': dj_database_url.config(
        default=preferred_database_url()
    )
}

# dj_database_url returns an empty dict if DATABASE_URL is set but blank; guard
# against that so Django always receives a valid ENGINE configuration.
if not DATABASES['default'].get('ENGINE'):
    DATABASES['default'] = dj_database_url.parse(DEFAULT_DATABASE_URL)

# --- ВАЛИДАТОРЫ ПАРОЛЕЙ ---
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- ИНТЕРНАЦИОНАЛИЗАЦИЯ ---
LANGUAGES = [
    ('ru', _('Русский')),
    ('pl', _('Polski')),
    ('en', _('English')),
]
LOCALE_PATHS = [os.path.join(BASE_DIR, 'locale')]
LANGUAGE_CODE = 'ru'
TIME_ZONE = 'Europe/Warsaw'
USE_I18N = True
USE_TZ = True

# --- СТАТИКА И МЕДИА (WHITENOISE) ---
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
if WHITENOISE_AVAILABLE:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# --- ДОПУСТИМЫЙ РАЗМЕР ЗАГРУЗОК ---
MAX_UPLOAD_SIZE_MB = int(os.environ.get('MAX_UPLOAD_SIZE_MB', '20'))
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE

# --- ПОЧТА (SendGrid или Brevo через API или SMTP) ---
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
BREVO_SMTP_PASSWORD = os.getenv("BREVO_SMTP_PASSWORD")
BREVO_SMTP_USER = os.getenv("BREVO_SMTP_USER", "apikey")
BREVO_SMTP_HOST = os.getenv("BREVO_SMTP_HOST", "smtp-relay.brevo.com")

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
    # Use a safer SMTP backend that falls back to console output if delivery fails
    EMAIL_BACKEND = "legalize_site.mail.SafeSMTPEmailBackend"

ANYMAIL = {}
if EMAIL_BACKEND == "anymail.backends.sendgrid.EmailBackend" and SENDGRID_API_KEY:
    ANYMAIL["SENDGRID_API_KEY"] = SENDGRID_API_KEY
if EMAIL_BACKEND == "anymail.backends.brevo.EmailBackend" and BREVO_API_KEY:
    ANYMAIL["BREVO_API_KEY"] = BREVO_API_KEY

# Обязательно укажи доменный адрес, подтверждённый в SendGrid (Domain Auth или Single Sender)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "nindse@gmail.com")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Куда уйдёт ответ на письмо
EMAIL_REPLY_TO = os.getenv("REPLY_TO_EMAIL", DEFAULT_FROM_EMAIL)

# --- DJANGO-ALLAUTH ---
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]
SITE_ID = 1

ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'

# Новые ключи (вместо устаревших ACCOUNT_AUTHENTICATION_METHOD / ACCOUNT_EMAIL_REQUIRED / ACCOUNT_USERNAME_REQUIRED)
ACCOUNT_LOGIN_METHODS = {"email"}  # логин только по email
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']  # поля регистрации

# Редиректы
LOGIN_URL = 'account_login'
LOGIN_REDIRECT_URL = reverse_lazy('clients:client_list')
LOGOUT_REDIRECT_URL = reverse_lazy('account_login')

# Соц. вход через Google (по желанию)
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
    }
}
