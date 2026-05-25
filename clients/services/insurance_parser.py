"""Utility helpers for extracting data from Insurance Policies (Polisa Ubezpieczeniowa)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from clients.services.wezwanie_parser import extract_text
from clients.services.company_parser import _find_detected_names, _clean_number, _find_valid_until_date

logger = logging.getLogger(__name__)

@dataclass
class InsuranceDocData:
    text: str
    error: str | None = None
    valid_until: date | None = None
    coverage_amount: float | None = None
    currency: str | None = None  # EUR or PLN
    detected_names: list[str] = field(default_factory=list)


def _find_coverage(text: str) -> tuple[float | None, str | None]:
    """Find coverage amount (e.g. 30000 EUR or 120000 PLN)."""
    # Look for sum insured / coverage keywords
    patterns = [
        # Match e.g. "suma ubezpieczenia: 30 000 EUR" or "suma gwarancyjna 150 000 PLN"
        re.compile(
            r"(?:suma\s*ubezpieczenia|suma\s*gwarancyjna|sum\s*insured|coverage|limit)[^\d\n]{0,40}?(\d{1,3}(?:[\s\u00a0]?\d{3})*(?:[.,]\d{2})?)\s*(EUR|PLN|USD|zł|zl|Euro)",
            re.IGNORECASE
        ),
        # Match number followed by EUR/PLN
        re.compile(
            r"\b(\d{1,3}(?:[\s\u00a0]?\d{3})*(?:[.,]\d{2})?)\s*(EUR|PLN|USD|zł|zl|Euro)\b",
            re.IGNORECASE
        )
    ]
    
    for pattern in patterns:
        for match in pattern.finditer(text):
            val = _clean_number(match.group(1))
            curr = match.group(2).upper()
            if curr in ("ZŁ", "ZL"):
                curr = "PLN"
            elif curr == "EURO":
                curr = "EUR"
                
            # Valid coverage amounts are usually high (>= 1000)
            if val and val >= 1000:
                return val, curr
                
    return None, None


def parse_insurance_doc(file_path: str | Path) -> InsuranceDocData:
    """Parse health insurance policy scan."""
    raw_text = extract_text(file_path)
    cleaned_text = raw_text.replace('\ufffe', '-').replace('\u00ad', '').replace('\ufeff', '')
    cleaned_text = cleaned_text.replace('\u00a0', ' ').replace('\t', ' ')
    cleaned_text = re.sub(r' +', ' ', cleaned_text).strip()

    if not cleaned_text:
        return InsuranceDocData(text="", error="no_text")

    valid_until = _find_valid_until_date(cleaned_text)
    coverage_amount, currency = _find_coverage(cleaned_text)
    detected_names = _find_detected_names(cleaned_text)

    return InsuranceDocData(
        text=cleaned_text,
        valid_until=valid_until,
        coverage_amount=coverage_amount,
        currency=currency,
        detected_names=detected_names
    )
