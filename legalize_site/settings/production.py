"""Production-only settings."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

from .base import env_flag
from .base import *  # noqa: F403

DEBUG = env_flag("DEBUG", "False")
if DEBUG:
    raise ImproperlyConfigured("DEBUG must remain False in production.")

ENABLE_TRANSLATION_TOOLING = env_flag("ENABLE_TRANSLATION_TOOLING", "False")

# --- HOSTS AND SECURITY ---
def _env_list(name: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


def _hostname_from_value(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value if "://" in value else f"//{value}")
    return parsed.hostname


def _origin_from_value(value: str | None, *, default_scheme: str = "https") -> str | None:
    if not value:
        return None
    parsed = urlparse(value if "://" in value else f"{default_scheme}://{value}")
    if not parsed.hostname:
        return None
    netloc = parsed.hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return f"{parsed.scheme or default_scheme}://{netloc}"


ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS")

RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
render_hostname = _hostname_from_value(RENDER_EXTERNAL_HOSTNAME)
if render_hostname:
    ALLOWED_HOSTS.append(render_hostname)
    CSRF_TRUSTED_ORIGINS.append(f"https://{render_hostname}")

RAILWAY_STATIC_URL = os.environ.get("RAILWAY_STATIC_URL")
railway_static_hostname = _hostname_from_value(RAILWAY_STATIC_URL)
railway_static_origin = _origin_from_value(RAILWAY_STATIC_URL)
if railway_static_hostname:
    ALLOWED_HOSTS.append(railway_static_hostname)
if railway_static_origin:
    CSRF_TRUSTED_ORIGINS.append(railway_static_origin)

RAILWAY_PUBLIC_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
railway_public_hostname = _hostname_from_value(RAILWAY_PUBLIC_DOMAIN)
if railway_public_hostname:
    ALLOWED_HOSTS.append(railway_public_hostname)
    CSRF_TRUSTED_ORIGINS.append(f"https://{railway_public_hostname}")

ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS))
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(CSRF_TRUSTED_ORIGINS))

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "ALLOWED_HOSTS must be configured in production via ALLOWED_HOSTS, "
        "RAILWAY_PUBLIC_DOMAIN, RAILWAY_STATIC_URL, or RENDER_EXTERNAL_HOSTNAME."
    )
if not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured(
        "CSRF_TRUSTED_ORIGINS must be configured in production via CSRF_TRUSTED_ORIGINS, "
        "RAILWAY_PUBLIC_DOMAIN, RAILWAY_STATIC_URL, or RENDER_EXTERNAL_HOSTNAME."
    )

# --- CACHE ---
REDIS_URL = os.environ.get("REDIS_URL")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }

# --- SECURITY HEADERS ---
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")
X_FRAME_OPTIONS = os.environ.get("X_FRAME_OPTIONS", "DENY")

if SESSION_COOKIE_SAMESITE.lower() == "none" and not SESSION_COOKIE_SECURE:
    raise ImproperlyConfigured("SESSION_COOKIE_SAMESITE=None requires SESSION_COOKIE_SECURE=True in production.")
if CSRF_COOKIE_SAMESITE.lower() == "none" and not CSRF_COOKIE_SECURE:
    raise ImproperlyConfigured("CSRF_COOKIE_SAMESITE=None requires CSRF_COOKIE_SECURE=True in production.")
