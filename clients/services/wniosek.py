from __future__ import annotations

from collections import defaultdict
import re
import unicodedata

from django.db import transaction
from django.utils import translation

from clients.constants import DocumentType
from clients.models import DocumentRequirement, WniosekAttachment, WniosekSubmission
from clients.models.document import _document_label_variants, resolve_document_label

ASCII_FALLBACK_MAP = str.maketrans(
    {
        "ł": "l",
        "ø": "o",
        "đ": "d",
        "ß": "ss",
        "æ": "ae",
        "œ": "oe",
    }
)

ATTACHMENT_ALIASES: dict[str, set[str]] = {
    DocumentType.EMPLOYER_TAX_RETURN.value: {
        "cit 8",
        "cit8",
        "pit 8",
        "pit8",
        "cit pracodawcy",
        "pit pracodawcy",
    },
}


def normalize_attachment_name(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""

    text = text.replace("№", " nr ")
    text = re.sub(r"\bno\.\b", " nr ", text, flags=re.IGNORECASE)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold()
    text = text.translate(ASCII_FALLBACK_MAP)
    text = re.sub(r"(?<=\d)(?=\D)|(?<=\D)(?=\d)", " ", text)
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split()).strip()


def clean_attachment_names(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    for value in values:
        text = " ".join(str(value or "").split()).strip()
        if not text:
            continue
        normalized = normalize_attachment_name(text)
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(text)

    return cleaned


def _tokens(value: str) -> set[str]:
    return {token for token in value.split() if token}


def _build_requirement_match_index(client, language: str | None = None) -> list[tuple[str, set[str]]]:
    language_codes = {"pl", "en", "ru"}
    active_language = (language or translation.get_language() or client.language or "pl").split("-")[0].lower()
    language_codes.add(active_language)

    requirements = {
        requirement.document_type: requirement
        for requirement in DocumentRequirement.objects.filter(application_purpose=client.application_purpose)
    }
    catalog = DocumentRequirement.catalog_for(
        client.application_purpose,
        active_language,
        include_optional=True,
        include_fallback=True,
    )

    index: list[tuple[str, set[str]]] = []
    for item in catalog:
        code = str(item["code"])
        variants: set[str] = set()

        requirement = requirements.get(code)
        variants.add(normalize_attachment_name(code))
        if requirement:
            for raw_value in (
                requirement.custom_name,
                requirement.custom_name_pl,
                requirement.custom_name_en,
                requirement.custom_name_ru,
            ):
                if raw_value:
                    variants.add(normalize_attachment_name(raw_value))

        for alias in ATTACHMENT_ALIASES.get(code, set()):
            variants.add(normalize_attachment_name(alias))

        for language_code in language_codes:
            label = resolve_document_label(
                code,
                requirement.custom_name if requirement else None,
                requirement.custom_name_pl if requirement else None,
                requirement.custom_name_en if requirement else None,
                requirement.custom_name_ru if requirement else None,
                language_code,
            )
            variants.add(normalize_attachment_name(label))

        variants.update(_document_label_variants(code))
        index.append((code, {variant for variant in variants if variant}))

    return index


def match_attachment_to_document_type(client, entered_name: str, language: str | None = None) -> str:
    normalized_name = normalize_attachment_name(entered_name)
    if not normalized_name:
        return ""

    index = _build_requirement_match_index(client, language)
    for code, variants in index:
        if normalized_name in variants:
            return code

    input_tokens = _tokens(normalized_name)
    if len(input_tokens) < 2:
        return ""

    candidates: list[tuple[int, int, str]] = []
    for code, variants in index:
        for variant in variants:
            variant_tokens = _tokens(variant)
            if not variant_tokens or not input_tokens.issubset(variant_tokens):
                continue
            candidates.append((len(input_tokens), -len(variant_tokens), code))
            break

    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][2]

    return ""


def resolve_attachment_document_type(client, attachment, language: str | None = None) -> str:
    if attachment.document_type:
        return attachment.document_type
    return match_attachment_to_document_type(client, attachment.entered_name, language)


def record_wniosek_submission(
    *,
    client,
    document_kind: str,
    attachment_names: list[str],
    confirmed_by=None,
    language: str | None = None,
) -> WniosekSubmission:
    cleaned_names = clean_attachment_names(attachment_names)
    with transaction.atomic():
        submission = WniosekSubmission.objects.create(
            client=client,
            document_kind=document_kind,
            attachment_count=len(cleaned_names),
            confirmed_by=confirmed_by,
        )

        for position, entered_name in enumerate(cleaned_names):
            WniosekAttachment.objects.create(
                submission=submission,
                document_type=match_attachment_to_document_type(client, entered_name, language),
                entered_name=entered_name,
                position=position,
            )

    return submission


def get_submitted_document_codes(client) -> set[str]:
    attachments = WniosekAttachment.objects.filter(submission__client=client).order_by("id")
    submitted_codes: set[str] = set()
    for attachment in attachments:
        resolved_code = resolve_attachment_document_type(client, attachment, client.language)
        if resolved_code:
            submitted_codes.add(resolved_code)
    return submitted_codes


def build_submitted_document_summary(client) -> dict[str, object]:
    attachments = (
        WniosekAttachment.objects.filter(submission__client=client)
        .select_related("submission", "submission__confirmed_by")
        .order_by("-submission__confirmed_at", "position", "id")
    )

    grouped_by_code: dict[str, list[dict[str, object]]] = defaultdict(list)
    custom_groups: dict[str, dict[str, object]] = {}

    for attachment in attachments:
        resolved_code = resolve_attachment_document_type(client, attachment, client.language)
        record = {
            "attachment_id": attachment.id,
            "entered_name": attachment.entered_name,
            "submitted_at": attachment.submission.confirmed_at,
            "document_kind": attachment.submission.get_document_kind_display(),
            "confirmed_by": attachment.submission.confirmed_by,
        }
        if resolved_code:
            grouped_by_code[resolved_code].append(record)
            continue

        custom_key = normalize_attachment_name(attachment.entered_name)
        if custom_key not in custom_groups:
            custom_groups[custom_key] = {
                "name": attachment.entered_name,
                "records": [],
            }
        custom_groups[custom_key]["records"].append(record)

    return {
        "codes": dict(grouped_by_code),
        "custom": list(custom_groups.values()),
    }
