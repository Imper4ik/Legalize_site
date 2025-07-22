"""
Django settings for legalize_site project.
"""

from pathlib import Path
import os
from django.utils.translation import gettext_lazy as _

LANGUAGES = [
    ('ru', _('Русский')),
    ('pl', _('Polski')),
    ('en', _('English')),
]

BASE_DIR = Path(__file__).resolve().parent.parent

LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'locale'),
]

SECRET_KEY = 'django-insecure-wr&zre@01k3+-y#r)sdv5itm2g3uw@hs8*=endlh+m5m$t8qc$'
DEBUG = False
ALLOWED_HOSTS = ['legalize-site.onrender.com', '127.0.0.1', 'localhost', '192.168.0.41']


EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.sendgrid.net'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', 'apikey')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')

DEFAULT_FROM_EMAIL = 'noreply@legalize-site.onrender.com'

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'clients',
    'portal',
    'django.contrib.humanize',
    'django.contrib.sites',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.middleware.locale.LocaleMiddleware',
]

ROOT_URLCONF = 'legalize_site.urls'

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
        },
    },
]

WSGI_APPLICATION = 'legalize_site.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Warsaw'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Django Allauth Settings ---

# Бэкенды аутентификации
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# ID сайта (обязательно для allauth)
SITE_ID = 1

# --- Настройки входа и регистрации по Email ---
ACCOUNT_AUTHENTICATION_METHOD = 'email'  # Устанавливаем метод входа по email
ACCOUNT_EMAIL_REQUIRED = True            # Делаем email обязательным для регистрации
ACCOUNT_USERNAME_REQUIRED = False        # Отключаем требование вводить "Имя пользователя" (username)
ACCOUNT_USER_MODEL_USERNAME_FIELD = None # Сообщаем allauth, что у нашей модели User нет поля username
ACCOUNT_EMAIL_VERIFICATION = 'optional'  # Верификация email (можно 'mandatory' или 'none')

# Адреса для перенаправлений
LOGIN_URL = 'account_login'
LOGIN_REDIRECT_URL = 'root_dashboard'
LOGOUT_REDIRECT_URL = 'account_login'

# Кастомная форма регистрации (если используется)
ACCOUNT_SIGNUP_FORM_CLASS = 'portal.forms.CustomSignupForm'

# Настройки для входа через соцсети (Google и др.)
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        }
    }
}

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'