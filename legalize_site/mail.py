"""Custom email backends used by the Legalize site project."""

import logging
from typing import Iterable

from django.core.mail import EmailMessage
from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend
from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend

logger = logging.getLogger(__name__)


class SafeSMTPEmailBackend(SMTPEmailBackend):
    """SMTP backend that gracefully falls back to the console backend.

    When SMTP credentials are misconfigured or unavailable we still want the
    password reset flow (and any other email-based workflows) to succeed
    locally without raising exceptions.  This backend first tries to deliver
    messages using the regular :class:`SMTPEmailBackend`.  If that fails we log
    the failure and render the messages through Django's console backend so the
    developer can see the email contents in the terminal.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Initialise a fallback console backend with the same settings Django
        # would otherwise pass to the main backend.
        self._fallback_backend = ConsoleEmailBackend(*args, **kwargs)

    def send_messages(self, email_messages: Iterable[EmailMessage] | None) -> int:
        if not email_messages:
            return 0

        try:
            return super().send_messages(email_messages)
        except Exception as exc:  # pragma: no cover - defensive safeguard
            logger.warning(
                "SMTP send failed, falling back to console email backend: %s",
                exc,
                exc_info=True,
            )
            return self._fallback_backend.send_messages(email_messages)
