"""Utility helpers for extracting data from ZUS documents (ZUS ZUA / ZUS ZCNA / ZUS RCA)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from clients.services.company_parser import _find_detected_names, _find_nip
from clients.services.wezwanie_parser import extract_text

logger = logging.getLogger(__name__)

# Known ZUS form types in order of specificity
_ZUS_FORM_TYPES = [
    "ZCNA",  # Zgłoszenie danych o członkach rodziny
    "ZIUA",  # Zgłoszenie zmiany danych identyfikacyjnych osoby ubezpieczonej
    "ZUA",   # Zgłoszenie do ubezpieczeń / zgłoszenie zmiany danych
    "ZZA",   # Zgłoszenie do ubezpieczenia zdrowotnego
    "ZWUA",  # Wyrejestrowanie z ubezpieczeń
    "RCA",   # Imienny raport miesięczny o należnych składkach
    "RSA",   # Imienny raport miesięczny o wypłaconych świadczeniach
    "RZA",   # Imienny raport miesięczny o należnych składkach na ubezpieczenie zdrowotne
    "DRA",   # Deklaracja rozliczeniowa
]


@dataclass
class ZusDocData:
    text: str
    error: str | None = None
    employer_nip: str | None = None
    insurance_code: str | None = None  # e.g., "011000"
    period_month: date | None = None  # normalized to the first day of the ZUS month
    detected_names: list[str] = field(default_factory=list)
    zus_form_type: str | None = None   # e.g., "ZUA", "ZCNA", "RCA"


_ACCENT_TRANSLATION = str.maketrans({
    "\u0142": "l",
    "\u0141": "l",
    "\u00f3": "o",
    "\u00d3": "o",
    "\u0105": "a",
    "\u0104": "a",
    "\u0107": "c",
    "\u0106": "c",
    "\u0119": "e",
    "\u0118": "e",
    "\u0144": "n",
    "\u0143": "n",
    "\u015b": "s",
    "\u015a": "s",
    "\u017a": "z",
    "\u0179": "z",
    "\u017c": "z",
    "\u017b": "z",
})


def _normalize_zus_text(text: str) -> str:
    return text.lower().translate(_ACCENT_TRANSLATION)


def _compact_insurance_code(raw_code: str) -> str:
    return re.sub(r"\D", "", raw_code)


def _detect_zus_form_type(text: str) -> str | None:
    """Detect which ZUS form type this document is (ZUA, ZCNA, RCA, etc.)."""
    upper = text.upper()
    normalized = _normalize_zus_text(text)

    # 1. Check by full official Polish form titles in normalized text
    if "zgloszenie do ubezpieczen" in normalized:
        return "ZUA"
    if "zgloszenie danych o czlonkach rodziny" in normalized:
        return "ZCNA"
    if "zgloszenie do ubezpieczenia zdrowotnego" in normalized:
        return "ZZA"
    if "wyrejestrowanie z ubezpieczen" in normalized:
        return "ZWUA"
    if "imienny raport miesieczny" in normalized:
        if "swiadczeniach" in normalized or "przerwach" in normalized:
            return "RSA"
        if "zdrowotne" in normalized and "spoleczne" not in normalized:
            return "RZA"
        return "RCA"
    if "deklaracja rozliczeniowa" in normalized:
        return "DRA"

    # 2. Match with ZUS prefix (allowing spaces/dots/dashes)
    for form_type in _ZUS_FORM_TYPES:
        pattern = rf"\bZUS\s*[.\-\s]*\s*{re.escape(form_type)}\b"
        if re.search(pattern, upper):
            return form_type

    # 3. Fallback: if text contains 'ZUS' anywhere, search for standalone form types
    if "ZUS" in upper or "ZAKLAD UBEZPIECZEN" in upper:
        for form_type in _ZUS_FORM_TYPES:
            if re.search(rf"\b{re.escape(form_type)}\b", upper):
                return form_type

    return None


def _find_insurance_code(text: str) -> str | None:
    """Find ZUS title insurance code without confusing PESEL/identifier values for it."""
    normalized = _normalize_zus_text(text)
    code_pattern = r"(\d{2}\s*\d{2}\s*\d{2})"
    contextual_patterns = [
        rf"kod\s+tyt(?:ulu|\.)?\s+ubezpieczenia[^\d]{{0,100}}{code_pattern}",
        rf"kod\s+tytulu[^\d]{{0,100}}{code_pattern}",
        rf"tytul\s+ubezpieczenia[^\d]{{0,100}}{code_pattern}",
        rf"kod[^\n]{{0,40}}ubezpieczenia[^\d]{{0,100}}{code_pattern}",
        # ZUA-specific: "V. TYTUŁ UBEZPIECZENIA" section header followed by code
        rf"v\.\s*tytul\s+ubezpieczenia[^\d]{{0,100}}{code_pattern}",
    ]
    for pattern in contextual_patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            code = _compact_insurance_code(match.group(1))
            if len(code) == 6:
                return code

    # Fallback only for known title-code prefixes. A broad "04xxxx" search is unsafe
    # because OCR often splits PESEL/identifier values under "04. IDENTYFIKATOR".
    # 0444 is a real kod tytułu ubezpieczenia in this workflow and must not be treated
    # as an OCR error.
    fallback_pattern = re.compile(r"(?<!\d)((?:0110|0411|0412|0444|0510)\s*\d{2})(?!\d)")
    match = fallback_pattern.search(normalized)
    if match:
        return _compact_insurance_code(match.group(1))

    return None


def _period_month(year: str, month: str) -> date | None:
    try:
        month_int = int(month)
        year_int = int(year)
        if 1 <= month_int <= 12 and 2000 <= year_int <= 2100:
            return date(year_int, month_int, 1)
    except (TypeError, ValueError):
        return None
    return None


def _find_zus_period_month(text: str) -> date | None:
    """Extract the ZUS RCA reporting month and normalize it to the first day.

    The parser prefers context-rich patterns to avoid treating normal dates such
    as upload/print dates as the RCA period. It still falls back to standalone
    MM.YYYY / YYYY-MM when the text looks like a ZUS report.
    """
    normalized = _normalize_zus_text(text)
    month = r"(0?[1-9]|1[0-2])"
    year = r"(20\d{2})"
    context = (
        r"(?:za\s+miesiac|miesiac|mies\.|okres\s+rozliczeniowy|"
        r"deklaracja\s+za|raport\s+za|rca\s+za|zus\s+rca\s+za)"
    )

    contextual_patterns = [
        rf"{context}[^\d]{{0,50}}{month}\s*[./\-\s]+{year}",
        rf"{context}[^\d]{{0,50}}{year}\s*[./\-\s]+{month}",
        # Real ZUS RCA/DRA layout: the reporting period is printed in the
        # "Identyfikator raportu/deklaracji" field as "nr miesiac rok",
        # e.g. "01 05 2026" (space-separated, no za miesiac keyword).
        rf"identyfikator\s+(?:raportu|deklaracji)[^\d]{{0,30}}\d{{2}}[.\-\s]+{month}[.\-\s]+{year}",
        # Labelled month/year fields: "Miesiac 05 ... Rok 2026".
        rf"miesiac[^\d]{{0,20}}{month}[^\d]{{0,20}}rok[^\d]{{0,20}}{year}",
    ]
    for pattern in contextual_patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue
        groups = match.groups()
        if len(groups) >= 2:
            # First pattern captures month, year; second captures year, month.
            if len(groups[0]) == 4:
                parsed = _period_month(groups[0], groups[1])
            else:
                parsed = _period_month(groups[1], groups[0])
            if parsed:
                return parsed

    looks_like_zus_rca = "zus" in normalized and bool(re.search(r"\brca\b", normalized))
    if not looks_like_zus_rca:
        return None

    # Avoid matching inside full dates like 25.05.2026 by requiring no digit/dot
    # immediately before the month.
    fallback_patterns = [
        rf"(?<![\d.]){month}\s*[./\-]\s*{year}\b",
        rf"\b{year}\s*[./\-]\s*{month}\b",
    ]
    for pattern in fallback_patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue
        groups = match.groups()
        if len(groups[0]) == 4:
            parsed = _period_month(groups[0], groups[1])
        else:
            parsed = _period_month(groups[1], groups[0])
        if parsed:
            return parsed

    return None


def _find_zcna_family_members(text: str) -> list[str]:
    """Extract family member names from ZUS ZCNA form.

    ZCNA has sections like "V. DANE O CZŁONKU RODZINY" with name fields.
    """
    names: list[str] = []
    normalized = _normalize_zus_text(text)

    # ZCNA typically lists family members under sections with "nazwisko" and "imię"
    member_patterns = [
        r"nazwisko\s*[:\-]?\s*([A-Za-z\u00C0-\u024F\s]+?)(?:\s{2,}|\n|imie|data)",
        r"czlonek\s+rodziny[^\n]*?([A-Z][a-z]+\s+[A-Z][a-z]+)",
    ]
    for pattern in member_patterns:
        for m in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            name = m.group(1).strip()
            if len(name) > 3 and name not in names:
                names.append(name)

    return names


def parse_zus_doc(file_path: str | Path) -> ZusDocData:
    """Parse ZUS document scan (supports ZUA, ZCNA, RCA, and other ZUS forms)."""
    raw_text = extract_text(file_path)
    cleaned_text = raw_text.replace('\ufffe', '-').replace('\u00ad', '').replace('\ufeff', '')
    cleaned_text = cleaned_text.replace('\u00a0', ' ').replace('\t', ' ')
    cleaned_text = re.sub(r' +', ' ', cleaned_text).strip()

    if not cleaned_text:
        return ZusDocData(text="", error="no_text")

    zus_form_type = _detect_zus_form_type(cleaned_text)
    employer_nip = _find_nip(cleaned_text)
    insurance_code = _find_insurance_code(cleaned_text)
    period_month = _find_zus_period_month(cleaned_text)
    detected_names = _find_detected_names(cleaned_text)

    # For ZCNA, also try to extract family member names
    if zus_form_type == "ZCNA":
        family_names = _find_zcna_family_members(cleaned_text)
        for name in family_names:
            if name not in detected_names:
                detected_names.append(name)

    logger.info(
        "ZUS document parsed: form_type=%s, nip=%s, insurance_code=%s, names=%d",
        zus_form_type,
        bool(employer_nip),
        insurance_code,
        len(detected_names),
    )

    return ZusDocData(
        text=cleaned_text,
        employer_nip=employer_nip,
        insurance_code=insurance_code,
        period_month=period_month,
        detected_names=detected_names,
        zus_form_type=zus_form_type,
    )
