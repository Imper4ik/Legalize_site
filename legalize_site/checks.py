"""Custom system checks for the Legalize site project."""

from __future__ import annotations

import os

from django.conf import settings
from django.core.checks import Error, Warning, register

EMAIL_ERROR_ID = "legalize_site.E001"
EMAIL_WARNING_ID = "legalize_site.W001"
EMAIL_CONSOLE_WARNING_ID = "legalize_site.W002"
SECRET_KEY_ERROR_ID = "legalize_site.E002"
FERNET_KEYS_ERROR_ID = "legalize_site.E003"
SECRET_KEY_WARNING_ID = "legalize_site.W003"
FERNET_KEYS_WARNING_ID = "legalize_site.W004"

BACKENDS = {
    "django.core.mail.backends.smtp.EmailBackend": {
        "mode": "smtp",
        "provider": "SendGrid",
        "env_var": "SENDGRID_API_KEY",
    },
    "anymail.backends.sendgrid.EmailBackend": {
        "mode": "api",
        "provider": "SendGrid",
        "env_var": "SENDGRID_API_KEY",
    },
    "anymail.backends.brevo.EmailBackend": {
        "mode": "api",
        "provider": "Brevo",
        "env_var": "BREVO_API_KEY",
    },
}


def _smtp_provider() -> str:
    """Return provider name inferred from EMAIL_HOST."""

    host = (settings.EMAIL_HOST or "").lower()
    if not host:
        return ""
    if "brevo" in host or "sendinblue" in host:
        return "Brevo"
    if "sendgrid" in host:
        return "SendGrid"
    return "custom"


@register("legalize_site")
def email_configuration_check(app_configs=None, **kwargs):
    """Validate the production email settings.

    Missing API keys cause runtime failures or silent console backends in
    production. Surfacing the misconfiguration early keeps password reset and
    activation emails working when deployments happen.
    """

    provider = None
    env_var = None
    mode = None

    messages = []

    if settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
        messages.append(
            Warning(
                "EMAIL_BACKEND is set to the console backend, so messages are "
                "only printed to logs and never delivered.",
                hint=(
                    "Set SENDGRID_API_KEY, BREVO_API_KEY or SMTP credentials via "
                    "environment variables to enable real email sending."
                ),
                id=EMAIL_CONSOLE_WARNING_ID,
            )
        )

        default_from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "")
        if default_from_email.endswith("yourdomain.tld"):
            messages.append(
                Warning(
                    "DEFAULT_FROM_EMAIL still uses the placeholder domain "
                    "'yourdomain.tld'.",
                    hint=(
                        "Set DEFAULT_FROM_EMAIL (or REPLY_TO_EMAIL) to a "
                        "provider-verified address via environment variables."
                    ),
                    id=EMAIL_WARNING_ID,
                )
            )

        return messages

    if settings.EMAIL_BACKEND in {
        "django.core.mail.backends.smtp.EmailBackend",
        "legalize_site.mail.SafeSMTPEmailBackend",
    }:
        provider = _smtp_provider()
        if provider == "Brevo":
            env_var = "BREVO_SMTP_PASSWORD"
        elif provider == "SendGrid":
            env_var = "SENDGRID_API_KEY"
        else:
            env_var = "EMAIL_HOST_PASSWORD"
        mode = "smtp"
    else:
        backend = BACKENDS.get(settings.EMAIL_BACKEND)
        if not backend:
            # Project does not use a supported email backend right now (e.g. when
            # running tests with the console backend). Skip validation to avoid
            # false positives.
            return []
        provider = backend["provider"]
        env_var = backend["env_var"]
        mode = backend["mode"]

    host_label = settings.EMAIL_HOST or "the SMTP host"
    provider_label = provider or "Email"
    if provider_label == "custom":
        provider_label = "SMTP"

    if mode == "api":
        api_key = getattr(settings, "ANYMAIL", {}).get(env_var) or os.getenv(env_var)
        hint = (
            f"Set the {env_var} environment variable so the anymail {provider_label} "
            "backend can authenticate against the provider API."
        )
        provider_label = f"{provider_label} API key"
    else:
        api_key = getattr(settings, "EMAIL_HOST_PASSWORD", None) or os.getenv(env_var)
        hint = (
            f"Set the {env_var} environment variable or provide a value for "
            f"settings.EMAIL_HOST_PASSWORD so Django can authenticate with "
            f"{host_label}."
        )
        provider_label = f"{provider_label} SMTP password" if provider_label != "Email" else "SMTP password"

    if not api_key:
        messages.append(
            Error(
                f"{provider_label} is not configured.",
                hint=hint,
                id=EMAIL_ERROR_ID,
            )
        )

    default_from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "")
    if default_from_email.endswith("yourdomain.tld"):
        messages.append(
            Warning(
                "DEFAULT_FROM_EMAIL still uses the placeholder domain "
                "'yourdomain.tld'.",
                hint=(
                    "Set DEFAULT_FROM_EMAIL (or REPLY_TO_EMAIL) to a "
                    "provider-verified address via environment variables."
                ),
                id=EMAIL_WARNING_ID,
            )
        )

    return messages


@register("legalize_site")
def encryption_configuration_check(app_configs=None, **kwargs):
    """Validate secret and encryption key configuration.

    In production, missing keys are hard errors (the app also refuses to start).
    In development/test, warnings surface the fact that PII encryption relies on
    a key derived from SECRET_KEY or that SECRET_KEY uses the insecure default.
    """

    messages = []
    placeholder_secret = "django-insecure-change-me"
    secret_key = getattr(settings, "SECRET_KEY", "")
    is_production = getattr(settings, "IS_PRODUCTION", False)
    fernet_configured = getattr(settings, "FERNET_KEYS_CONFIGURED", False)

    if is_production and (not secret_key or secret_key == placeholder_secret):
        messages.append(
            Error(
                "SECRET_KEY must be configured explicitly in production.",
                hint="Set a strong SECRET_KEY environment variable for the production deployment.",
                id=SECRET_KEY_ERROR_ID,
            )
        )
    elif not is_production and secret_key == placeholder_secret:
        messages.append(
            Warning(
                "SECRET_KEY is using the insecure default fallback value.",
                hint=(
                    "Set SECRET_KEY to a unique value for safer local development.  "
                    "In production this will be an error."
                ),
                id=SECRET_KEY_WARNING_ID,
            )
        )

    if is_production and not fernet_configured:
        messages.append(
            Error(
                "FERNET_KEYS must be configured explicitly in production.",
                hint=(
                    "Set FERNET_KEYS to one or more Fernet keys and do not rely on keys "
                    "derived from SECRET_KEY."
                ),
                id=FERNET_KEYS_ERROR_ID,
            )
        )
    elif not is_production and not fernet_configured:
        messages.append(
            Warning(
                "FERNET_KEYS environment variable is not set; "
                "encryption keys are derived from SECRET_KEY.",
                hint=(
                    "Set FERNET_KEYS to explicit Fernet keys for safer "
                    "PII encryption.  In production this will be an error."
                ),
                id=FERNET_KEYS_WARNING_ID,
            )
        )

    return messages
