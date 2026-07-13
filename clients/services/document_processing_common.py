"""Shared result types and constants for document upload / OCR processing.

Extracted from ``document_workflow`` so the upload facade, the job queue and
the per-type processors can share them without import cycles.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Callable

from django.utils.translation import gettext as _

from clients.models import Document, DocumentProcessingJob
from clients.services.wezwanie_parser import WezwanieData

logger = logging.getLogger(__name__)

DEFAULT_JOB_LEASE_SECONDS = 600
DEFAULT_JOB_MAX_ATTEMPTS = 3

MANUAL_WEZWANIE_REVIEW_MESSAGE = _(
    "Document uploaded, but automatic wezwanie parsing failed. Manual review is required."
)

Parser = Callable[[str], WezwanieData]
# Senders are called as ``sender(client)`` and, when supported, ``sender(client,
# case=...)``; ``_send_notification`` falls back on TypeError. Use an open
# signature so the optional keyword is well-typed.
NotificationSender = Callable[..., int]


@dataclass
class DocumentUploadResult:
    document: Document
    message: str
    manual_review_required: bool = False
    pending_confirmation: bool = False
    ocr_processing_queued: bool = False
    parsed_payload: dict[str, Any] | None = None


@dataclass
class WezwanieConfirmationResult:
    document: Document
    message: str
    manual_review_required: bool = False


@dataclass
class DocumentProcessingRunResult:
    job: DocumentProcessingJob
    status: str
    processed: bool
    message: str = ""
    manual_review_required: bool = False
    auto_updates: list[str] = field(default_factory=list)


def _document_file_identity(document: Document) -> str:
    """Stable non-PII token used to detect whether a queued file changed."""

    source_name = document.file.name or ""
    if not source_name:
        return ""
    return sha256(source_name.encode("utf-8")).hexdigest()

def _job_matches_processing_state(
    job: DocumentProcessingJob,
    document: Document,
    source_file_name: str,
) -> bool:
    current_file_identity = _document_file_identity(document)
    return (
        job.status == DocumentProcessingJob.STATUS_PROCESSING
        and job.source_file_name == source_file_name
        and source_file_name in {current_file_identity, document.file.name or ""}
    )
