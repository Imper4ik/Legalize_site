"""Development-only settings."""

from __future__ import annotations

import os

from .base import env_flag
from .base import *  # noqa: F403

DEBUG = env_flag("DEBUG", "True")

ALLOWED_HOSTS = [host for host in os.environ.get("ALLOWED_HOSTS", "").split(",") if host]
ALLOWED_HOSTS.extend(["127.0.0.1", "localhost"])

CSRF_TRUSTED_ORIGINS = [
    origin for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if origin
]

SECURE_SSL_REDIRECT = False
