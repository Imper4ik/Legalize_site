"""Utility helpers for extracting data from Wezwanie summons scans."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


DATE_FORMATS = ("%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d")
CASE_NUMBER_PATTERNS = (
    re.compile(r"numer\s+sprawy[:\s]*([-A-Za-z0-9./ ]+)", re.IGNORECASE),
    re.compile(r"nr\s+sprawy[:\s]*([-A-Za-z0-9./ ]+)", re.IGNORECASE),
    re.compile(r"sygn\.\s*akt[:\s]*([-A-Za-z0-9./ ]+)", re.IGNORECASE),
    re.compile(r"\b([A-Z]{1,3}\/?\d{1,4}/\d{2,4})\b"),
)
DATE_PATTERNS = (
    re.compile(r"(?:dniu|dnia|dn\.)?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})", re.IGNORECASE),
    re.compile(r"(\d{4}-\d{2}-\d{2})"),
)


@dataclass
class WezwanieData:
    """Parsed data extracted from the uploaded summons."""

    text: str
    case_number: str | None = None
    fingerprints_date: date | None = None


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None

    cleaned = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def _extract_pdf_text(path: Path) -> str:
    try:
        data = path.read_bytes()
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("Не удалось прочитать PDF %s", path)
        return ""

    # На случай, если файл содержит текстовые фрагменты в читабельном виде,
    # пробуем извлечь их напрямую.
    try:
        return data.decode("utf-8", errors="ignore")
    except Exception:  # pragma: no cover - defensive safeguard
        return ""


def _read_plain_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("Не удалось прочитать файл %s как текст", path)
        return ""


def extract_text(path: str | Path) -> str:
    """Extract raw text from the uploaded summons file.

    Prefers PDF parsing when the file has a PDF extension. Falls back to a
    simple text read when parsing fails or for non-PDF files.
    """

    file_path = Path(path)

    text = ""
    if file_path.suffix.lower() == ".pdf":
        text = _extract_pdf_text(file_path)

    if not text:
        text = _read_plain_text(file_path)

    return text


def _find_case_number(text: str) -> str | None:
    for pattern in CASE_NUMBER_PATTERNS:
        match = pattern.search(text)
        if match:
            normalized = re.sub(r"[^A-Za-z0-9./-]", "", match.group(1)).upper()
            if normalized:
                return normalized
    return None


def _find_first_date(text: str) -> date | None:
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            parsed = _parse_date(match.group(1))
            if parsed:
                return parsed
    return None


def parse_wezwanie(file_path: str | Path) -> WezwanieData:
    """Parse the uploaded summons and return the extracted fields."""

    text = extract_text(file_path)
    case_number = _find_case_number(text)
    fingerprints_date = _find_first_date(text)

    return WezwanieData(text=text, case_number=case_number, fingerprints_date=fingerprints_date)
