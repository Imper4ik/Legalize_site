"""Custom system checks for the Legalize site project."""

from __future__ import annotations

import os

from django.conf import settings
from django.core.checks import Error, Warning, register

SENDGRID_ERROR_ID = "legalize_site.E001"
SENDGRID_WARNING_ID = "legalize_site.W001"


@register("legalize_site")
def sendgrid_configuration_check(app_configs=None, **kwargs):
    """Validate the SendGrid related Django email settings.

    The application relies on Django's SMTP backend to talk to SendGrid.
    Misconfigured credentials cause runtime ``SMTPAuthenticationError``
    exceptions which surface as HTTP 500 responses when a view attempts to
    send mail.  By raising a system check error early we make the
    misconfiguration obvious during deployment (``manage.py check``) and in
    CI.
    """

    backend_mode = {
        "django.core.mail.backends.smtp.EmailBackend": "smtp",
        "anymail.backends.sendgrid.EmailBackend": "api",
    }.get(settings.EMAIL_BACKEND)

    if not backend_mode:
        # Project does not use a SendGrid related backend right now (e.g. when
        # running tests with the console backend). Skip the SendGrid specific
        # validation to avoid false positives.
        return []

    messages = []
    if backend_mode == "api":
        api_key = getattr(settings, "ANYMAIL", {}).get("SENDGRID_API_KEY") or os.getenv("SENDGRID_API_KEY")
        hint = (
            "Set the SENDGRID_API_KEY environment variable so the "
            "anymail SendGrid backend can authenticate when calling the "
            "SendGrid Web API."
        )
    else:
        api_key = getattr(settings, "EMAIL_HOST_PASSWORD", None) or os.getenv("SENDGRID_API_KEY")
        hint = (
            "Set the SENDGRID_API_KEY environment variable or provide a "
            "value for settings.EMAIL_HOST_PASSWORD so Django can "
            "authenticate with smtp.sendgrid.net."
        )

    if not api_key:
        messages.append(
            Error(
                "SendGrid API key is not configured.",
                hint=hint,
                id=SENDGRID_ERROR_ID,
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
                    "SendGrid-verified address via environment variables."
                ),
                id=SENDGRID_WARNING_ID,
            )
        )

    return messages
