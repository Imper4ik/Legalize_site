from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, cast, TYPE_CHECKING

from django.conf import settings
from django.db import transaction
from django.utils import translation
from django.utils.translation import gettext as _

from clients.constants import DocumentType
from clients.models import Client, DocumentRequirement, WniosekAttachment, WniosekSubmission

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser


logger = logging.getLogger(__name__)

ATTACHMENT_ALIASES = {
    "zalacznik nr 1": DocumentType.ZALACZNIK_NR_1.value,
    "zalacznik 1": DocumentType.ZALACZNIK_NR_1.value,
    "zal nr 1": DocumentType.ZALACZNIK_NR_1.value,
    "zal 1": DocumentType.ZALACZNIK_NR_1.value,
    "zus rca": DocumentType.ZUS_RCA_OR_INSURANCE.value,
    "zus": DocumentType.ZUS_RCA_OR_INSURANCE.value,
    "cit 8": DocumentType.EMPLOYER_TAX_RETURN.value,
    "cit8": DocumentType.EMPLOYER_TAX_RETURN.value,
    "pit 8": DocumentType.EMPLOYER_TAX_RETURN.value,
    "pit8": DocumentType.EMPLOYER_TAX_RETURN.value,
}


def _normalize_attachment_label(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    normalized = without_marks.casefold().replace("_", " ")
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def _candidate_labels_for_code(code: str, label: str) -> set[str]:
    candidates = {
        code,
        code.replace("_", " "),
        label,
    }
    return {_normalize_attachment_label(candidate) for candidate in candidates if candidate}


def match_attachment_to_document_type(client: Client, entered_name: str, language: str | None = None) -> str:
    """Map a free-form wniosek attachment label back to a checklist code."""

    normalized_name = _normalize_attachment_label(entered_name)
    if not normalized_name:
        return ""

    alias_match = ATTACHMENT_ALIASES.get(normalized_name)
    if alias_match:
        return str(alias_match)

    languages = []
    if language:
        languages.append(language)
    if client.language and client.language not in languages:
        languages.append(client.language)
    languages.extend(code for code, _label in getattr(settings, "LANGUAGES", []) if code not in languages)

    purpose = client.get_document_requirement_purpose()
    best_match = ""
    best_match_length = 0
    for language_code in languages or [None]:
        for item in DocumentRequirement.catalog_for(
            purpose,
            language_code,
            include_optional=True,
            include_fallback=True,
        ):
            code = str(item["code"])
            for candidate in _candidate_labels_for_code(code, str(item["label"])):
                if normalized_name == candidate:
                    return code
                if len(candidate) >= 4 and (
                    normalized_name in candidate or candidate in normalized_name
                ) and len(candidate) > best_match_length:
                    best_match = code
                    best_match_length = len(candidate)

    return best_match


def clean_attachment_names(attachment_names: list[str]) -> list[str]:
    """Remove empty strings, strip whitespace, and dedupe preserving order."""

    cleaned: list[str] = []
    seen: set[str] = set()
    for name in attachment_names:
        stripped = name.strip() if name else ""
        if not stripped:
            continue
        normalized = _normalize_attachment_label(stripped)
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(stripped)
    return cleaned


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
                document_type=match_attachment_to_document_type(
                    client,
                    entered_name,
                    language,
                ),
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
    """Get document codes submitted via all wnioseks."""

    return set(build_submitted_document_summary(client)["codes"].keys())


def _submitted_record(attachment: WniosekAttachment, document_type: str = "") -> dict[str, Any]:
    submission = attachment.submission
    return {
        "attachment_id": attachment.pk,
        "submission_id": submission.pk,
        "submitted_at": submission.confirmed_at,
        "confirmed_by": submission.confirmed_by,
        "entered_name": attachment.entered_name,
        "document_type": document_type or attachment.document_type,
    }


def build_submitted_document_summary(client: Client) -> dict[str, Any]:
    """Build a summary of all submitted documents for the client."""
    attachments = WniosekAttachment.objects.filter(
        submission__client=client
    ).select_related("submission", "submission__confirmed_by")
    
    codes: dict[str, list[dict[str, Any]]] = {}
    custom: list[dict[str, Any]] = []
    for att in attachments:
        document_type = att.document_type or match_attachment_to_document_type(
            client,
            att.entered_name,
            client.language,
        )
        record = _submitted_record(att, document_type)
        if document_type:
            codes.setdefault(document_type, []).append(record)
        else:
            custom.append(
                {
                    "name": att.entered_name,
                    "records": [record],
                }
            )
        
    return {
        "count": sum(len(records) for records in codes.values()) + len(custom),
        "codes": codes,
        "custom": custom,
    }
