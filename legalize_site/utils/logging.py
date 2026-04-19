"""Logging helpers for the Legalize site project."""

from __future__ import annotations

import logging
import re
from typing import Iterable


REDACTION_TOKEN = "[REDACTED]"


def redact_text(message: str) -> str:
    """Best-effort redaction for common PII patterns in free-form log strings."""

    redacted = str(message)
    field_patterns: Iterable[tuple[re.Pattern[str], str]] = (
        (
            re.compile(
                r"(?i)\b(passport(?:_?num)?|case(?:_?number)?|email|phone|full_name|first_name|last_name|raw_text|ocr_text|authorization|token|api_?key|secret|password)\b"
                r"(\s*[:=]\s*)([^\s,;]+)"
            ),
            rf"\1\2{REDACTION_TOKEN}",
        ),
        (
            re.compile(
                r"(?i)(['\"]?(?:passport(?:_?num)?|case(?:_?number)?|email|phone|full_name|first_name|last_name|raw_text|ocr_text|authorization|token|api_?key|secret|password)['\"]?\s*:\s*['\"])(.*?)(['\"])"
            ),
            rf"\1{REDACTION_TOKEN}\3",
        ),
    )
    generic_patterns: Iterable[tuple[re.Pattern[str], str]] = (
        (
            re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
            REDACTION_TOKEN,
        ),
        (
            re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{6,}\d)(?!\w)"),
            REDACTION_TOKEN,
        ),
        (
            re.compile(r"\b[A-Z]{1,3}\d{5,9}\b", re.IGNORECASE),
            REDACTION_TOKEN,
        ),
        (
            re.compile(r"\b(?:WSC|WSO)[-A-Z0-9./ ]{6,}\b", re.IGNORECASE),
            REDACTION_TOKEN,
        ),
        (
            re.compile(r"\b[A-Z]{1,5}[/-]\d{1,6}[/-]\d{2,4}\b", re.IGNORECASE),
            REDACTION_TOKEN,
        ),
        (
            re.compile(r"(?i)\bBearer\s+[A-Z0-9._-]{10,}\b"),
            f"Bearer {REDACTION_TOKEN}",
        ),
    )

    for pattern, replacement in field_patterns:
        redacted = pattern.sub(replacement, redacted)
    for pattern, replacement in generic_patterns:
        redacted = pattern.sub(replacement, redacted)
    return redacted


class RedactPIIFilter(logging.Filter):
    """Redact PII from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = redact_text(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True
