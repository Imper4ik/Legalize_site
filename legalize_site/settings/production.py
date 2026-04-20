"""Production-only settings."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from .base import env_flag
from .base import *  # noqa: F403

DEBUG = env_flag("DEBUG", "False")

ALLOWED_HOSTS = [host for host in os.environ.get("ALLOWED_HOSTS", "").split(",") if host]
ALLOWED_HOSTS.append("legalize-site-production-740f.up.railway.app")
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

CSRF_TRUSTED_ORIGINS = [
    origin for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if origin
]
CSRF_TRUSTED_ORIGINS.append("https://legalize-site-production-740f.up.railway.app")
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

RAILWAY_STATIC_URL = os.environ.get("RAILWAY_STATIC_URL")
if RAILWAY_STATIC_URL:
    parsed = urlparse(RAILWAY_STATIC_URL)
    if parsed.hostname:
        ALLOWED_HOSTS.append(parsed.hostname)
        scheme = parsed.scheme or "https"
        CSRF_TRUSTED_ORIGINS.append(f"{scheme}://{parsed.hostname}")

RAILWAY_PUBLIC_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
if RAILWAY_PUBLIC_DOMAIN:
    hostname = RAILWAY_PUBLIC_DOMAIN.replace("https://", "").replace("http://", "")
    if hostname:
        ALLOWED_HOSTS.append(hostname)
        CSRF_TRUSTED_ORIGINS.append(f"https://{hostname}")

ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS))
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(CSRF_TRUSTED_ORIGINS))

# За прокси (Render) — чтобы Django корректно видел HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = os.environ.get("SECURE_REFERRER_POLICY", "same-origin")
SECURE_CROSS_ORIGIN_OPENER_POLICY = os.environ.get(
    "SECURE_CROSS_ORIGIN_OPENER_POLICY",
    "same-origin",
)
X_FRAME_OPTIONS = os.environ.get("X_FRAME_OPTIONS", "DENY")

SECURE_SSL_REDIRECT = env_flag("SECURE_SSL_REDIRECT", "True")
if SECURE_SSL_REDIRECT:
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "3600"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = os.environ.get("SECURE_HSTS_PRELOAD", "True").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
