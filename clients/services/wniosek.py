from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, cast, TYPE_CHECKING

from django.db import transaction
from django.utils import translation
from django.utils.translation import gettext as _

from clients.models import Client, WniosekAttachment, WniosekSubmission

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser


logger = logging.getLogger(__name__)


def clean_attachment_names(attachment_names: list[str]) -> list[str]:
    """Remove empty strings and strip whitespace."""
    return [name.strip() for name in attachment_names if name and name.strip()]


def create_wniosek_submission(
    *,
    client: Client,
    document_kind: str,
    attachment_names: list[str],
    confirmed_by: AbstractBaseUser | AnonymousUser | None = None,
    language: str | None = None,
) -> WniosekSubmission:
    cleaned_names = clean_attachment_names(attachment_names)
    
    # AnonymousUser cannot be assigned to ForeignKey
    creator = confirmed_by if confirmed_by and confirmed_by.is_authenticated else None
    
    with transaction.atomic():
        submission = WniosekSubmission.objects.create(
            client=client,
            document_kind=document_kind,
            attachment_count=len(cleaned_names),
            confirmed_by=cast(Any, creator),
        )

        for position, entered_name in enumerate(cleaned_names):
            WniosekAttachment.objects.create(
                submission=submission,
                entered_name=entered_name,
                position=position,
            )

    return submission

# Alias for compatibility with existing code
record_wniosek_submission = create_wniosek_submission


def get_wniosek_context(submission: WniosekSubmission, language: str | None = None) -> dict[str, Any]:
    """Prepare data for the PDF generation or display."""
    if language:
        translation.activate(language)

    attachments = submission.attachments.all().order_by("position")
    
    return {
        "submission": submission,
        "client": submission.client,
        "attachments": attachments,
        "date": submission.confirmed_at.date(),
        "document_kind_display": _(submission.document_kind.replace("_", " ").capitalize()),
    }


def find_matching_attachments(client: Client, submission: WniosekSubmission) -> dict[int, Any]:
    """
    Attempt to match entered attachment names with actual uploaded documents.
    Returns a dict mapping attachment ID to the matched Document object or None.
    """
    matches: dict[int, Any] = {}
    docs = list(client.documents.filter(verified=True))
    
    for attachment in submission.attachments.all():
        best_match = None
        # Simple heuristic: if the document name is contained in the entered name or vice versa
        for doc in docs:
            doc_label = str(doc.display_name).lower()
            entered_label = attachment.entered_name.lower()
            if doc_label in entered_label or entered_label in doc_label:
                best_match = doc
                break
        matches[attachment.pk] = best_match
        
    return matches


def get_submitted_document_codes(client: Client) -> set[str]:
    """Get a unique set of all document names/codes submitted via all wnioseks."""
    return set(
        WniosekAttachment.objects.filter(submission__client=client)
        .values_list("entered_name", flat=True)
    )


def build_submitted_document_summary(client: Client) -> dict[str, Any]:
    """Build a summary of all submitted documents for the client."""
    attachments = WniosekAttachment.objects.filter(
        submission__client=client
    ).select_related("submission")
    
    codes = {}
    for att in attachments:
        codes[att.entered_name] = {
            "submission_id": att.submission_id,
            "date": att.submission.confirmed_at.isoformat(),
        }
        
    return {
        "count": len(codes),
        "codes": codes,
    }
