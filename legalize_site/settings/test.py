from .development import *

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Use in-memory email backend for tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Static files configuration for tests
STATIC_URL = "/static/"
