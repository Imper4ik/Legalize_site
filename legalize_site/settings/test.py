import os

os.environ.setdefault("ENABLE_TRANSLATION_TOOLING", "True")

from .base import *

ENABLE_TRANSLATION_TOOLING = True

if "translations" not in INSTALLED_APPS:
    INSTALLED_APPS.append("translations")

if "translations.middleware.TranslationStudioMiddleware" not in MIDDLEWARE:
    insert_at = MIDDLEWARE.index("allauth.account.middleware.AccountMiddleware")
    MIDDLEWARE.insert(insert_at, "translations.middleware.TranslationStudioMiddleware")

# Force in-memory SQLite for tests to ignore Railway's DATABASE_URL during build phase
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Use in-memory email backend for tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Static files configuration for tests
STATIC_URL = "/static/"
