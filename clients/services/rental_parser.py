"""Utility helpers for extracting data from Rental Agreements (Umowa najmu)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from clients.services.wezwanie_parser import extract_text
from clients.services.company_parser import _find_detected_names, _clean_number

logger = logging.getLogger(__name__)

@dataclass
class RentalDocData:
    text: str
    error: str | None = None
    address: str | None = None
    valid_until: date | None = None
    monthly_cost: float | None = None
    detected_names: list[str] = field(default_factory=list)


def _find_address(text: str) -> str | None:
    """Find Polish address pattern (postcode + city/street) in the text."""
    # Look for postcode pattern: 12-345
    postcode_match = re.search(r"\b(\d{2}-\d{3})\b", text)
    if postcode_match:
        # Extract surrounding context containing the postcode
        pos = postcode_match.start()
        start = max(0, pos - 60)
        end = min(len(text), pos + 80)
        context = text[start:end].replace("\n", " ").strip()
        
        # Try to isolate address around postcode:
        # e.g., "ul. Marszałkowska 10/12 m. 5, 00-590 Warszawa"
        address_pattern = re.compile(
            r"((?:ul\.|ulica|al\.|aleja|pl\.|plac)?[^\d\n,]{2,30}\d+[-\w/\s]*(?:lok\.|lokal|m\.|mieszkania)?\s*\d*,\s*\d{2}-\d{3}\s+[^\s\n,]{2,30})",
            re.IGNORECASE
        )
        match = address_pattern.search(context)
        if match:
            return match.group(1).strip()
            
        # Fallback: return a chunk around the postcode
        return context

    # Simple fallback: look for street keywords
    street_match = re.search(r"\b(?:ul\.|ulica|al\.)\s+([A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż\s\d/-]+(?:lok\.|m\.)?\s*\d*)", text)
    if street_match:
        return street_match.group(0).strip()

    return None


def _find_rental_cost(text: str) -> float | None:
    # Look for payments near keywords like czynsz, najm, opłat
    patterns = [
        re.compile(
            r"(?:czynsz|najmu|kwot[ay]|opłat[ay])[^\d\n]{0,40}?(\d{1,3}(?:[\s\u00a0]?\d{3})*(?:[.,]\d{2})?)",
            re.IGNORECASE
        ),
        re.compile(
            r"\b(\d{1,3}(?:[\s\u00a0]?\d{3})*(?:[.,]\d{2})?)\s*(?:PLN|zł|zl)\b",
            re.IGNORECASE
        ),
    ]
    candidates = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            val = _clean_number(match.group(1))
            # Rental cost is usually between 200 and 15000 PLN
            if val and 200 <= val <= 15000:
                candidates.append(val)
                
    if candidates:
        # Return the most likely rental amount (often the first one or highest near keywords)
        return candidates[0]
    return None


def parse_rental_doc(file_path: str | Path) -> RentalDocData:
    """Parse rental agreement document."""
    raw_text = extract_text(file_path)
    cleaned_text = raw_text.replace('\ufffe', '-').replace('\u00ad', '').replace('\ufeff', '')
    cleaned_text = cleaned_text.replace('\u00a0', ' ').replace('\t', ' ')
    cleaned_text = re.sub(r' +', ' ', cleaned_text).strip()

    if not cleaned_text:
        return RentalDocData(text="", error="no_text")

    address = _find_address(cleaned_text)
    
    # Expiry Date: look for "do" followed by a date, or oznaczony "do dnia"
    from clients.services.company_parser import _find_valid_until_date
    valid_until = _find_valid_until_date(cleaned_text)
    
    monthly_cost = _find_rental_cost(cleaned_text)
    detected_names = _find_detected_names(cleaned_text)

    return RentalDocData(
        text=cleaned_text,
        address=address,
        valid_until=valid_until,
        monthly_cost=monthly_cost,
        detected_names=detected_names
    )
