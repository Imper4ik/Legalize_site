"""Logging helpers for the Legalize site project."""

from __future__ import annotations

import logging
import re
from typing import Iterable


class RedactPIIFilter(logging.Filter):
    """Redact PII from log messages."""

    _patterns: Iterable[re.Pattern[str]] = (
        re.compile(r"(?i)(passport_num|case_number)=([^\s,;]+)"),
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = message
        for pattern in self._patterns:
            redacted = pattern.sub(r"\1=[REDACTED]", redacted)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True
