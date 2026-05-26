"""Utility helpers for extracting data from Passports."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from clients.services.wezwanie_parser import extract_text, _parse_date

logger = logging.getLogger(__name__)

@dataclass
class PassportDocData:
    text: str
    error: str | None = None
    passport_number: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    valid_until: date | None = None
    country: str | None = None


def _parse_mrz(text: str) -> dict[str, Any] | None:
    """Attempt to parse MRZ (Machine Readable Zone) from passport text."""
    # Find two lines of 44 characters containing a lot of '<'
    lines = [line.strip().replace(" ", "") for line in text.splitlines()]
    mrz_lines = []
    for line in lines:
        if len(line) >= 40 and ("P<" in line or (line.count("<") > 5 and re.match(r"^[A-Z0-9<]+$", line))):
            mrz_lines.append(line)

    if len(mrz_lines) < 2:
        return None

    # Clean lines to be exactly their alphabetical uppercase representation
    line1 = mrz_lines[-2].upper()
    line2 = mrz_lines[-1].upper()

    # Sometimes MRZ is read with typos, let's fix common ones
    line1 = line1.replace("0", "O").replace("1", "I")
    
    # Check if first line starts with P
    p_idx = line1.find("P<")
    if p_idx == -1:
        return None
    line1 = line1[p_idx:]
    
    if len(line1) < 30 or len(line2) < 30:
        return None

    result: dict[str, Any] = {}
    try:
        # Line 1: P<COUNTRYLASTNAME<<FIRSTNAME<<<<<
        country = line1[2:5].replace("<", "")
        result["country"] = country

        name_part = line1[5:]
        if "<<" in name_part:
            parts = name_part.split("<<", 1)
            last_name = parts[0].replace("<", " ").strip().title()
            first_name = parts[1].replace("<", " ").strip().title()
            result["first_name"] = first_name
            result["last_name"] = last_name

        # Line 2: PassportNum (9) + CheckDigit + Country (3) + DOB (6) + CheckDigit + Sex + Expiry (6)
        # Often the document number is 9 chars
        doc_num = line2[0:9].replace("<", "")
        result["passport_number"] = doc_num

        # DOB (YYMMDD) - chars 13 to 19 (0-indexed)
        dob_raw = line2[13:19]
        if re.match(r"^\d{6}$", dob_raw):
            # Guess century: if YY > current year - 10, assume 1900s, else 2000s
            yy = int(dob_raw[0:2])
            current_year = datetime.now().year % 100
            century = 1900 if yy > current_year else 2000
            dob_str = f"{century + yy}-{dob_raw[2:4]}-{dob_raw[4:6]}"
            try:
                result["date_of_birth"] = date.fromisoformat(dob_str)
            except ValueError:
                pass

        # Expiry Date (YYMMDD) - chars 21 to 27
        exp_raw = line2[21:27]
        if re.match(r"^\d{6}$", exp_raw):
            yy = int(exp_raw[0:2])
            # Expiry is future, so assume 2000s
            exp_str = f"20{yy:02d}-{exp_raw[2:4]}-{exp_raw[4:6]}"
            try:
                result["valid_until"] = date.fromisoformat(exp_str)
            except ValueError:
                pass

        return result
    except Exception as e:
        logger.warning("Failed to parse MRZ: %s", e)
        return None


def _find_passport_number(text: str) -> str | None:
    # Look for patterns like "Passport No. XX1234567" or "Nr dokumentu / Document No."
    patterns = [
        re.compile(r"(?:passport\s*no|nr\s*paszportu|nr\s*dokumentu|document\s*no)[^\s]{0,5}\s*([a-z]{1,3}\d{6,8})\b", re.IGNORECASE),
        re.compile(r"\b([a-z]{2}\d{7})\b", re.IGNORECASE), # common Polish passport format: 2 letters, 7 digits
        re.compile(r"\b([a-z]{1}\d{8})\b", re.IGNORECASE), # other formats
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(1).upper()
    return None


def _find_dob(text: str) -> date | None:
    # Look for birth date keywords
    patterns = [
        re.compile(r"(?:data\s*urodzenia|date\s*of\s*birth|birth\s*date|urodz)[^\d\n]{0,20}(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2})", re.IGNORECASE),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            parsed = _parse_date(match.group(1))
            if parsed:
                return parsed
    return None


def _find_expiry(text: str) -> date | None:
    # Look for expiry keywords
    patterns = [
        re.compile(r"(?:data\s*ważności|expiry\s*date|valid\s*until|ważny\s*do|do\s*dnia)[^\d\n]{0,20}(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2})", re.IGNORECASE),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            parsed = _parse_date(match.group(1))
            if parsed:
                return parsed
    return None


def parse_passport_doc(file_path: str | Path) -> PassportDocData:
    """Parse passport document scan."""
    raw_text = extract_text(file_path)
    cleaned_text = raw_text.replace('\ufffe', '-').replace('\u00ad', '').replace('\ufeff', '')
    cleaned_text = cleaned_text.replace('\u00a0', ' ').replace('\t', ' ')
    cleaned_text = re.sub(r' +', ' ', cleaned_text).strip()

    if not cleaned_text:
        return PassportDocData(text="", error="no_text")

    # 1. Try parsing MRZ first (very accurate if MRZ exists)
    mrz_data = _parse_mrz(cleaned_text)
    if mrz_data:
        return PassportDocData(
            text=cleaned_text,
            passport_number=mrz_data.get("passport_number"),
            first_name=mrz_data.get("first_name"),
            last_name=mrz_data.get("last_name"),
            date_of_birth=mrz_data.get("date_of_birth"),
            valid_until=mrz_data.get("valid_until"),
            country=mrz_data.get("country")
        )

    # 2. Fallback to regex checks
    passport_number = _find_passport_number(cleaned_text)
    date_of_birth = _find_dob(cleaned_text)
    valid_until = _find_expiry(cleaned_text)

    # Try extracting names by checking capitalized pairs (excluding labels)
    # Since names are hard to isolate without MRZ, we'll return the detected names as fallback list in first/last
    from clients.services.company_parser import _find_detected_names
    detected = _find_detected_names(cleaned_text)
    first_name = None
    last_name = None
    if detected:
        # Assume first detected name is First Last name
        parts = detected[0].split()
        if len(parts) >= 2:
            first_name = parts[0]
            last_name = parts[-1]

    return PassportDocData(
        text=cleaned_text,
        passport_number=passport_number,
        first_name=first_name,
        last_name=last_name,
        date_of_birth=date_of_birth,
        valid_until=valid_until
    )
