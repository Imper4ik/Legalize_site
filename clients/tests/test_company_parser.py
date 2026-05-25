from __future__ import annotations

from datetime import date
import pytest

from clients.services.company_parser import (
    validate_nip,
    _find_nip,
    _find_krs,
    _find_salary,
    _find_valid_until_date,
    _find_detected_names,
)

def test_validate_nip():
    # Valid Polish NIP (Google Poland Sp. z o.o.)
    assert validate_nip("5252344078") is True
    # Invalid NIP
    assert validate_nip("1234567890") is False


def test_find_nip():
    # Standard format with spaces/dashes
    text = "Dane firmy: NIP: 525-23-44-078, KRS 0000123456"
    assert _find_nip(text) == "5252344078"

    # Digits only
    text_digits = "NIP 5252344078 details"
    assert _find_nip(text_digits) == "5252344078"

    # Fallback to checksum search when label is missing/garbled
    text_garbled = "Firma MOCK, numer identyfikacyjny 5252344078. KRS 0000123456"
    assert _find_nip(text_garbled) == "5252344078"


def test_find_krs():
    text = "Sąd Rejestrowy: KRS: 0000123456"
    assert _find_krs(text) == "0000123456"

    # Fallback (any 10-digit starting with 0000)
    text_fallback = "Numer rejestru to 0000987654 в Варшаве"
    assert _find_krs(text_fallback) == "0000987654"


def test_find_salary():
    # In Polish Załącznik context
    text1 = "wysokość wynagrodzenia: 4 300,00 PLN brutto"
    assert _find_salary(text1) == 4300.0

    text2 = "kwota wynagrodzenia wynosi 5250.50 zl miesiecznie"
    assert _find_salary(text2) == 5250.5

    # Currency format
    text3 = "stawka: 3500 PLN"
    assert _find_salary(text3) == 3500.0


def test_find_valid_until_date():
    text = "Umowa zawarta na czas określony do dnia 31.12.2026 r."
    assert _find_valid_until_date(text) == date(2026, 12, 31)

    text_iso = "okres zatrudnienia do 2027-06-30"
    assert _find_valid_until_date(text_iso) == date(2027, 6, 30)


def test_find_detected_names():
    text = "W imieniu pracodawcy działa Jan Kowalski. Pełnomocnik Darya Afanasenka. Warszawa, 2026."
    names = _find_detected_names(text)
    assert "Jan Kowalski" in names
    assert "Darya Afanasenka" in names
    # Ensure "Warszawa" (excluded city) or other uppercase words aren't returned
    assert "Warszawa 2026" not in names
