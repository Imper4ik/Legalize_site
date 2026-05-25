"""Utility helpers for extracting data from ZUS documents (ZUS ZUA / ZUS RCA)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
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
    detected_names: list[str] = field(default_factory=list)


_ACCENT_TRANSLATION = str.maketrans({
    "\u0142": "l",
    "\u0141": "l",
    "\u00f3": "o",
    "\u00d3": "o",
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

    # Fallback only for common title-code prefixes. A broad "04xxxx" search is unsafe
    # because OCR often splits PESEL/identifier values under "04. IDENTYFIKATOR".
    fallback_pattern = re.compile(r"(?<!\d)((?:0110|0411|0510)\s*\d{2})(?!\d)")
    match = fallback_pattern.search(normalized)
    if match:
        return _compact_insurance_code(match.group(1))

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
    detected_names = _find_detected_names(cleaned_text)

    return ZusDocData(
        text=cleaned_text,
        employer_nip=employer_nip,
        insurance_code=insurance_code,
        detected_names=detected_names
    )
