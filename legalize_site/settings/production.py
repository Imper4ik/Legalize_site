"""Production-only settings."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import env_flag

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
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": os.environ.get("DJANGO_CACHE_TABLE", "cache_table"),
        }
    }

# --- SECURITY HEADERS ---
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_flag("SECURE_SSL_REDIRECT", "True")
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
PERMISSIONS_POLICY = {
    "camera": "()",
    "microphone": "()",
    "geolocation": "()",
    "payment": "()",
    "usb": "()",
    "interest-cohort": "()",
}
SECURE_PERMISSIONS_POLICY = ", ".join(f"{k}={v}" for k, v in PERMISSIONS_POLICY.items())
CONTENT_SECURITY_POLICY = {
    "default-src": ("'self'",),
    "base-uri": ("'self'",),
    "object-src": ("'none'",),
    "frame-ancestors": ("'none'",),
    "form-action": ("'self'",),
    "img-src": ("'self'", "data:", "blob:"),
    "font-src": ("'self'", "data:", "https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com"),
    "style-src": ("'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com"),
    # script-src no longer relies on 'unsafe-inline': every inline <script> in our
    # own templates (and allauth) carries nonce="{{ request.csp_nonce }}", and the
    # CSP middleware injects that per-request nonce into this directive. Verified
    # that staff pages, allauth, and Django admin have no un-nonced executable
    # inline scripts. style-src keeps 'unsafe-inline' until inline style="" usages
    # are refactored. (audit P-02)
    "script-src": ("'self'", "https://cdn.jsdelivr.net"),
    "connect-src": ("'self'",),
}
LEGALIZE_CONTENT_SECURITY_POLICY = "; ".join(
    f"{directive} {' '.join(sources)}"
    for directive, sources in CONTENT_SECURITY_POLICY.items()
)
LEGALIZE_CSP_REPORT_ONLY = env_flag("LEGALIZE_CSP_REPORT_ONLY", "False")

# Opt-in stricter CSP, emitted in Report-Only mode alongside the enforced policy.
# Drops 'unsafe-inline' from script/style so the browser reports every inline
# script/style/handler without breaking anything — the inventory step before
# enforcing the strict policy for real (A3). Default off; enable to collect data.
LEGALIZE_CSP_STRICT_REPORT_ONLY = env_flag("LEGALIZE_CSP_STRICT_REPORT_ONLY", "False")
LEGALIZE_CONTENT_SECURITY_POLICY_REPORT_ONLY = ""
if LEGALIZE_CSP_STRICT_REPORT_ONLY:
    STRICT_CONTENT_SECURITY_POLICY = {
        **CONTENT_SECURITY_POLICY,
        "style-src": ("'self'", "https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com"),
        "script-src": ("'self'", "https://cdn.jsdelivr.net"),
    }
    LEGALIZE_CONTENT_SECURITY_POLICY_REPORT_ONLY = "; ".join(
        f"{directive} {' '.join(sources)}"
        for directive, sources in STRICT_CONTENT_SECURITY_POLICY.items()
    )

if SESSION_COOKIE_SAMESITE.lower() == "none" and not SESSION_COOKIE_SECURE:
    raise ImproperlyConfigured("SESSION_COOKIE_SAMESITE=None requires SESSION_COOKIE_SECURE=True in production.")
if CSRF_COOKIE_SAMESITE.lower() == "none" and not CSRF_COOKIE_SECURE:
    raise ImproperlyConfigured("CSRF_COOKIE_SAMESITE=None requires CSRF_COOKIE_SECURE=True in production.")
