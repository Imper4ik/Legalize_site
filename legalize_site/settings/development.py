"""Development-only settings."""

from __future__ import annotations

import os

from .base import *  # noqa: F403
from .base import env_flag

DEBUG = env_flag("DEBUG", "True")
ENABLE_TRANSLATION_TOOLING = env_flag("ENABLE_TRANSLATION_TOOLING", "True")
ASYNC_OCR_PROCESSING = False
# Local dev has no separate job runner; keep auto-OCR inline for instant feedback.
ASYNC_AUTO_OCR_PROCESSING = False

ALLOWED_HOSTS = [host for host in os.environ.get("ALLOWED_HOSTS", "").split(",") if host]
ALLOWED_HOSTS.extend(["127.0.0.1", "localhost"])

CSRF_TRUSTED_ORIGINS = [
    origin for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if origin
]

SECURE_SSL_REDIRECT = False
