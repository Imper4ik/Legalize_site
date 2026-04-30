import os

os.environ.setdefault("ENABLE_TRANSLATION_TOOLING", "True")

from .base import *  # noqa: F403

ENABLE_TRANSLATION_TOOLING = True

if "translations" not in INSTALLED_APPS:  # noqa: F405
    INSTALLED_APPS.append("translations")  # noqa: F405

if "translations.middleware.TranslationStudioMiddleware" not in MIDDLEWARE:  # noqa: F405
    insert_at = MIDDLEWARE.index("allauth.account.middleware.AccountMiddleware")  # noqa: F405
    MIDDLEWARE.insert(insert_at, "translations.middleware.TranslationStudioMiddleware")  # noqa: F405

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
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}  # noqa: F405
