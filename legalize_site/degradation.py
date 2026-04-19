"""Unified service degradation policy for the Legalize site project.

Defines how the application should behave when external dependencies
are unavailable.  Use these constants in views and services to enforce
consistent graceful degradation across the codebase.

Usage example::

    from legalize_site.degradation import ServicePolicy

    if not ocr_available():
        if ServicePolicy.OCR == DegradationMode.GRACEFUL:
            document.needs_manual_review = True
            document.save()
"""

from __future__ import annotations

from enum import Enum


class DegradationMode(str, Enum):
    """How to handle a service outage."""

    GRACEFUL = "graceful"
    """Service failure is silently tolerated; alternative path is activated.

    Example: OCR unavailable → document is uploaded, flagged for manual review.
    """

    QUEUE_RETRY = "queue_retry"
    """Operation is queued for later retry with logging.

    Example: Email delivery failed → re-queue and retry, notify admin.
    """

    FALLBACK_WARN = "fallback_warn"
    """Use a cached/default value and display a user-facing warning.

    Example: Exchange rate API unavailable → use last-known rate, warn user.
    """

    ERROR_ALERT = "error_alert"
    """Fail the specific operation and alert administrators, but keep the
    rest of the application running.

    Example: Database backup failed → log error + admin alert, app continues.
    """


class ServicePolicy:
    """Mapping of external services to their degradation mode.

    Centralises decisions so developers don't have to reinvent error
    handling for each integration point.
    """

    OCR: DegradationMode = DegradationMode.GRACEFUL
    """Tesseract/Poppler unavailable → upload works, manual review flag set."""

    EMAIL: DegradationMode = DegradationMode.QUEUE_RETRY
    """SMTP/API delivery error → queue + retry, log failure."""

    EXCHANGE_RATE: DegradationMode = DegradationMode.FALLBACK_WARN
    """External rate API unavailable → use last cached rate + user warning."""

    BACKUP: DegradationMode = DegradationMode.ERROR_ALERT
    """pg_dump / storage failure → error + admin alert, app stays up."""
