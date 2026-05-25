"""Utility helpers for extracting data from ZUS documents (ZUS ZUA / ZUS RCA)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from clients.services.wezwanie_parser import extract_text
from clients.services.company_parser import _find_nip, _find_detected_names

logger = logging.getLogger(__name__)


@dataclass
class ZusDocData:
    text: str
    error: str | None = None
    employer_nip: str | None = None
    insurance_code: str | None = None  # e.g., "011000"
    period_month: date | None = None  # normalized to the first day of the ZUS month
    detected_names: list[str] = field(default_factory=list)


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


def _find_insurance_code(text: str) -> str | None:
    """Find ZUS title insurance code without confusing PESEL/identifier values for it."""
    normalized = _normalize_zus_text(text)
    code_pattern = r"(\d{2}\s*\d{2}\s*\d{2})"
    contextual_patterns = [
        rf"kod\s+tyt(?:ulu|\.)?\s+ubezpieczenia[^\d]{{0,100}}{code_pattern}",
        rf"kod\s+tytulu[^\d]{{0,100}}{code_pattern}",
        rf"tytul\s+ubezpieczenia[^\d]{{0,100}}{code_pattern}",
        rf"kod[^\n]{{0,40}}ubezpieczenia[^\d]{{0,100}}{code_pattern}",
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

    looks_like_zus_rca = "zus" in normalized and "rca" in normalized
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


def parse_zus_doc(file_path: str | Path) -> ZusDocData:
    """Parse ZUS document scan."""
    raw_text = extract_text(file_path)
    cleaned_text = raw_text.replace('\ufffe', '-').replace('\u00ad', '').replace('\ufeff', '')
    cleaned_text = cleaned_text.replace('\u00a0', ' ').replace('\t', ' ')
    cleaned_text = re.sub(r' +', ' ', cleaned_text).strip()

    if not cleaned_text:
        return ZusDocData(text="", error="no_text")

    employer_nip = _find_nip(cleaned_text)
    insurance_code = _find_insurance_code(cleaned_text)
    period_month = _find_zus_period_month(cleaned_text)
    detected_names = _find_detected_names(cleaned_text)

    return ZusDocData(
        text=cleaned_text,
        employer_nip=employer_nip,
        insurance_code=insurance_code,
        period_month=period_month,
        detected_names=detected_names,
    )
