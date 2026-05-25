"""Utility helpers for extracting data from company documents (Załącznik nr 1, Umowa)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from clients.services.wezwanie_parser import extract_text, _parse_date

logger = logging.getLogger(__name__)

EXCLUDE_WORDS = {
    "Warszawa", "Kraków", "Łódź", "Wrocław", "Poznań", "Gdańsk", "Szczecin", "Bydgoszcz", "Lublin",
    "Styczeń", "Stycznia", "Luty", "Lutego", "Marzec", "Marca", "Kwiecień", "Kwietnia", "Maj", "Maja",
    "Czerwiec", "Czerwca", "Lipiec", "Lipca", "Sierpień", "Sierpnia", "Wrzesień", "Września",
    "Październik", "Października", "Listopad", "Listopada", "Grudzień", "Grudnia",
    "Rzeczypospolitej", "Polskiej", "Polsce", "PESEL", "NIP", "KRS", "REGON", "Załącznik", "Umowa",
    "Dyrektor", "Prezes", "Zarząd", "Prokurent", "Pracodawca", "Pracownik", "Spółka", "Obywatel",
    "Pan", "Pani", "Obywatelstwo", "PESEL", "NIP", "KRS", "REGON", "Zalacznik", "Zobowiązuje",
    "Oświadczam", "Oswiadczam", "Minister", "Ministerstwo", "Urząd", "Urzad", "Wojewoda",
    "Wojewódzki", "Wojewodzki", "Rada", "Polska", "Polski", "Pracy", "Zatrudnieniu", "Krajowy",
    "Krajowego", "Sąd", "Sad", "Sądu", "Sadu", "Rejestr", "Rejestru", "Sądowego", "Sadowego",
    "Ubezpieczeń", "Ubezpieczen", "Społecznych", "Spolecznych", "Zakład", "Zaklad",
    "Styczniu", "Lutym", "Marcu", "Kwietniu", "Maju", "Czerwcu", "Lipcu", "Sierpniu", "Wrześniu",
    "Październiku", "Listopadzie", "Grudniu",
    "Pełnomocnik", "Pelnomocnik", "Podpis", "Czytelny", "Miejscowość", "Miejscowosc", "Data", "Dnia",
    "Rok", "Firma", "Firmy", "Nazwa", "Adres", "Siedziba", "Siedziby", "Regon", "Krs", "Nip",
    "Spolka", "Ograniczoną", "Ograniczona", "Odpowiedzialnością", "Odpowiedzialnoscia", "Sp", "Zoo"
}

@dataclass
class CompanyDocData:
    """Parsed data extracted from a company document."""

    text: str
    error: str | None = None
    nip: str | None = None
    krs: str | None = None
    salary: float | None = None
    valid_until: date | None = None
    detected_names: list[str] = field(default_factory=list)


def validate_nip(nip: str) -> bool:
    """Validate Polish NIP checksum."""
    digits = [int(c) for c in nip if c.isdigit()]
    if len(digits) != 10:
        return False
    weights = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    checksum = sum(d * w for d, w in zip(digits[:-1], weights)) % 11
    return checksum == digits[-1]


def _find_nip(text: str) -> str | None:
    """Find valid NIP in the text."""
    # 1. Search for "NIP" label within 30 characters of a digit sequence
    pattern = re.compile(r"\b(?:NIP|N\.I\.P\.)\b[^\d\n]{0,30}(\d[\d\-\s]{8,16}\d)\b", re.IGNORECASE)
    for match in pattern.finditer(text):
        cleaned = re.sub(r"[^\d]", "", match.group(1))
        if len(cleaned) == 10 and validate_nip(cleaned):
            return cleaned

    # 2. General fallback: scan any digit sequence in the text
    candidates = re.findall(r"\b\d[\d\-\s]{8,16}\d\b", text)
    for c in candidates:
        cleaned = re.sub(r"[^\d]", "", c)
        if len(cleaned) == 10 and validate_nip(cleaned):
            return cleaned

    return None


def _find_krs(text: str) -> str | None:
    """Find KRS number in the text."""
    # 1. Search for "KRS" labels followed by 10 digits
    pattern = re.compile(r"\b(?:KRS|K\.R\.S\.)\b[:\s\-]*(\d{10})\b", re.IGNORECASE)
    match = pattern.search(text)
    if match:
        return match.group(1)

    # 2. General fallback: look for 10-digit number starting with 0000 or 000
    candidates = re.findall(r"\b(000\d{7})\b", text)
    if candidates:
        return candidates[0]

    return None


def _clean_number(raw: str) -> float | None:
    """Convert number string to float."""
    cleaned = raw.replace(" ", "").replace("\u00a0", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _find_salary(text: str) -> float | None:
    """Extract salary from document text."""
    # 1. Search for numbers near salary keywords
    pattern1 = re.compile(
        r"(?:wynagrodzen\w+|brutto|płac\w+|stawk\w+|kwot\w+)[^\d\n]{0,40}?(\d{1,3}(?:[\s\u00a0]?\d{3})*(?:[.,]\d{2})?)",
        re.IGNORECASE
    )
    # 2. Search for numbers followed by currency
    pattern2 = re.compile(
        r"\b(\d{1,3}(?:[\s\u00a0]?\d{3})*(?:[.,]\d{2})?)\s*(?:PLN|zł|zl|z\u0142otych)\b",
        re.IGNORECASE
    )

    candidates = []
    for match in pattern1.finditer(text):
        val = _clean_number(match.group(1))
        if val and 1000 <= val <= 200000:
            candidates.append((val, 0))  # Higher priority

    for match in pattern2.finditer(text):
        val = _clean_number(match.group(1))
        if val and 1000 <= val <= 200000:
            candidates.append((val, 1))  # Lower priority

    if candidates:
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]

    return None


def _find_valid_until_date(text: str) -> date | None:
    """Find the validity date of the document/contract."""
    # Search for dates after "do", "do dnia", "okres do"
    pattern = re.compile(
        r"\bdo\s+(?:dnia\s+)?(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2})",
        re.IGNORECASE
    )
    for match in pattern.finditer(text):
        parsed = _parse_date(match.group(1))
        if parsed:
            return parsed
    return None


def _find_detected_names(text: str) -> list[str]:
    """Find potential names (First Last) in the text."""
    # Split text into word-like tokens using regex (supporting Polish characters)
    words = re.findall(r"\b[a-zA-Ząćęłńóśźż\u0105\u0107\u0119\u0142\u0144\u00f3\u015b\u017a\u017c\u0104\u0106\u0118\u0141\u0143\u00d3\u015a\u0179\u017b]+\b", text)

    unique_candidates = []
    for i in range(len(words) - 1):
        w1 = words[i]
        w2 = words[i+1]

        # Check if both are capitalized or all-caps
        is_cap1 = w1 and w1[0].isupper() and (w1[1:].islower() or w1.isupper() or len(w1) == 1)
        is_cap2 = w2 and w2[0].isupper() and (w2[1:].islower() or w2.isupper() or len(w2) == 1)

        if is_cap1 and is_cap2:
            name1 = w1.capitalize()
            name2 = w2.capitalize()

            # Check exclusions (in different cases)
            if name1 in EXCLUDE_WORDS or name2 in EXCLUDE_WORDS:
                continue
            if w1.upper() in EXCLUDE_WORDS or w2.upper() in EXCLUDE_WORDS:
                continue

            fullname = f"{name1} {name2}"
            if fullname not in unique_candidates:
                unique_candidates.append(fullname)

    return unique_candidates


def parse_company_doc(file_path: str | Path) -> CompanyDocData:
    """Parse the uploaded company document and extract relevant fields."""
    raw_text = extract_text(file_path)
    # Normalizing text
    cleaned_text = raw_text.replace('\ufffe', '-').replace('\u00ad', '').replace('\ufeff', '')
    cleaned_text = cleaned_text.replace('\u00a0', ' ').replace('\t', ' ')
    cleaned_text = re.sub(r' +', ' ', cleaned_text).strip()

    if not cleaned_text:
        return CompanyDocData(text="", error="no_text")

    nip = _find_nip(cleaned_text)
    krs = _find_krs(cleaned_text)
    salary = _find_salary(cleaned_text)
    valid_until = _find_valid_until_date(cleaned_text)
    detected_names = _find_detected_names(cleaned_text)

    return CompanyDocData(
        text=cleaned_text,
        nip=nip,
        krs=krs,
        salary=salary,
        valid_until=valid_until,
        detected_names=detected_names,
    )
