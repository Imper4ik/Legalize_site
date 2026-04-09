"""Custom email backends used by the Legalize site project."""

import logging
from typing import Iterable

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend
from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend

logger = logging.getLogger(__name__)


class SafeSMTPEmailBackend(SMTPEmailBackend):
    """SMTP backend with an opt-in console fallback for development.

    In development it is useful to see the email contents in the console when
    SMTP is unavailable. In production that behavior is misleading because the
    application can report success even though the provider rejected delivery.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._allow_console_fallback = getattr(
            settings,
            "EMAIL_FALLBACK_TO_CONSOLE",
            False,
        )
        self._fallback_backend = ConsoleEmailBackend(*args, **kwargs)

    def send_messages(self, email_messages: Iterable[EmailMessage] | None) -> int:
        if not email_messages:
            return 0

        try:
            return super().send_messages(email_messages)
        except Exception as exc:  # pragma: no cover - defensive safeguard
            if not self._allow_console_fallback:
                logger.exception("SMTP send failed and console fallback is disabled")
                raise
            logger.warning(
                "SMTP send failed, falling back to console email backend: %s",
                exc,
                exc_info=True,
            )
            return self._fallback_backend.send_messages(email_messages)
