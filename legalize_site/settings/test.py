import os

os.environ.setdefault("ENABLE_TRANSLATION_TOOLING", "True")
if not os.environ.get("FERNET_KEYS"):
    os.environ["FERNET_KEYS"] = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="

from .base import *  # noqa: F403

ENABLE_TRANSLATION_TOOLING = True
TESTING = True

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
if "STORAGES" not in locals():
    STORAGES = {}
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
STORAGES["default"] = {"BACKEND": "django.core.files.storage.FileSystemStorage"}

# Keep test-generated files in writable, disposable directories.
TEST_ARTIFACTS_DIR = BASE_DIR / "tmp" / "test-artifacts"  # noqa: F405
MEDIA_ROOT = TEST_ARTIFACTS_DIR / "media"
STATIC_ROOT = TEST_ARTIFACTS_DIR / "staticfiles"
FILE_UPLOAD_TEMP_DIR = TEST_ARTIFACTS_DIR / "uploads"
for _path in (MEDIA_ROOT, STATIC_ROOT, FILE_UPLOAD_TEMP_DIR):
    os.makedirs(_path, exist_ok=True)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "legalize-tests",
    }
}

EMAIL_SEND_RETRY_BACKOFF_SECONDS = 0
EMAIL_CAMPAIGN_RETRY_BACKOFF_SECONDS = 0
EMAIL_CAMPAIGN_BATCH_DELAY_SECONDS = 0
