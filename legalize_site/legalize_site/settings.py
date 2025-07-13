"""
Django settings for legalize_site project.
"""

from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-wr&zre@01k3+-y#r)sdv5itm2g3uw@hs8*=endlh+m5m$t8qc$'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Ваши приложения
    'clients',
    'django.contrib.humanize',

    # Приложения для Allauth
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
    # Middleware от Allauth
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'legalize_site.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],  # Указываем глобальную папку для шаблонов
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

# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]

# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'ru-ru'  # Рекомендую сменить на 'ru-ru'

TIME_ZONE = 'Europe/Warsaw'  # Рекомендую сменить на ваш часовой пояс

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = 'static/'

# Media files (User-uploaded files)
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Настройки для django-allauth ---
AUTHENTICATION_BACKENDS = [
    # Нужен для входа в админку с логином и паролем
    'django.contrib.auth.backends.ModelBackend',
    # Нужен для аутентификации через allauth (email, соц. сети)
    'allauth.account.auth_backends.AuthenticationBackend',
]

SITE_ID = 1

# URL-адреса для перенаправлений
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'client_list'
LOGOUT_REDIRECT_URL = 'client_list'

# --- САМЫЕ СОВРЕМЕННЫЕ НАСТРОЙКИ ALLAUTH ---

# Способ входа: только по email
ACCOUNT_AUTHENTICATION_METHOD = 'email'
# Поля, которые будут запрашиваться при регистрации
ACCOUNT_SIGNUP_FIELDS = ['email']
# Не требуем подтверждения email для простоты
ACCOUNT_EMAIL_VERIFICATION = 'none'
# Автоматически создавать пользователя после входа через соц. сеть
SOCIALACCOUNT_AUTO_SIGNUP = True

# Настройки для провайдера Google
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