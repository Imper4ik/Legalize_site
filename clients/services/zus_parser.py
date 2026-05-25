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


def _find_insurance_code(text: str) -> str | None:
    """Find ZUS insurance code (6 digits, e.g., 011000 or 01 10 00)."""
    # Standard code for employment is 011000 (0110xx)
    pattern = re.compile(r"\b(01\s*10\s*\d{2})\b")
    match = pattern.search(text)
    if match:
        return match.group(1).replace(" ", "")
        
    # Generic 6-digit code search
    pattern_generic = re.compile(r"\b(\d{6})\b")
    for match in pattern_generic.finditer(text):
        code = match.group(1)
        # ZUS codes usually start with 01, 04, 05, etc.
        if code.startswith(("01", "04", "05", "30", "50")):
            return code
            
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
