"""Logging helpers for the Legalize site project."""

from __future__ import annotations

import logging
import re
from contextvars import ContextVar
from typing import Iterable


REDACTION_TOKEN = "[REDACTED]"
_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
_correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")


def set_log_context(*, request_id: str | None = None, correlation_id: str | None = None) -> None:
    if request_id is not None:
        _request_id_var.set(request_id)
    if correlation_id is not None:
        _correlation_id_var.set(correlation_id)


def clear_log_context() -> None:
    _request_id_var.set("-")
    _correlation_id_var.set("-")


def get_request_id() -> str:
    return _request_id_var.get()


def get_correlation_id() -> str:
    return _correlation_id_var.get()


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


class RequestContextFilter(logging.Filter):
    """Inject request-scoped IDs into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        record.correlation_id = get_correlation_id()
        return True
