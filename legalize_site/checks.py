"""Custom system checks for the Legalize site project."""

from __future__ import annotations

import os

from django.conf import settings
from django.core.checks import Error, Warning, register

EMAIL_ERROR_ID = "legalize_site.E001"
EMAIL_WARNING_ID = "legalize_site.W001"
EMAIL_CONSOLE_WARNING_ID = "legalize_site.W002"

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
    if "brevo" in host or "sendinblue" in host:
        return "Brevo"
    return "SendGrid"


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

    if settings.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend":
        provider = _smtp_provider()
        env_var = "BREVO_SMTP_PASSWORD" if provider == "Brevo" else "SENDGRID_API_KEY"
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

    if mode == "api":
        api_key = getattr(settings, "ANYMAIL", {}).get(env_var) or os.getenv(env_var)
        hint = (
            f"Set the {env_var} environment variable so the anymail {provider} "
            "backend can authenticate against the provider API."
        )
    else:
        api_key = getattr(settings, "EMAIL_HOST_PASSWORD", None) or os.getenv(env_var)
        hint = (
            f"Set the {env_var} environment variable or provide a value for "
            f"settings.EMAIL_HOST_PASSWORD so Django can authenticate with "
            f"{settings.EMAIL_HOST}."
        )

    if not api_key:
        messages.append(
            Error(
                f"{provider} API key is not configured.",
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
