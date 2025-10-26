# legalize_site/settings.py

from pathlib import Path
import importlib.util
from django.utils.translation import gettext_lazy as _
from django.urls import reverse_lazy
import dj_database_url
import os

WHITENOISE_AVAILABLE = importlib.util.find_spec('whitenoise') is not None

# --- БАЗОВЫЕ НАСТРОЙКИ ---
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-change-me')
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = [host for host in os.environ.get('ALLOWED_HOSTS', '').split(',') if host]
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
ALLOWED_HOSTS.extend(['127.0.0.1', 'localhost'])

CSRF_TRUSTED_ORIGINS = [origin for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if origin]
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

# За прокси (Render) — чтобы Django корректно видел HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

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

    'clients',

    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
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

# --- БАЗА ДАННЫХ (НАСТРОЕНО ДЛЯ RENDER) ---
DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
    )
}

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
LANGUAGE_CODE = 'ru-ru'
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

# --- ПОЧТА (SMTP SendGrid) ---
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.sendgrid.net"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = "apikey"  # именно строка 'apikey'
EMAIL_HOST_PASSWORD = os.getenv("SENDGRID_API_KEY")  # ключ из переменных окружения Render
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@yourdomain.tld")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
# Удобно иметь для Reply-To (используется в send_mail(..., reply_to=[EMAIL_REPLY_TO]))
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
