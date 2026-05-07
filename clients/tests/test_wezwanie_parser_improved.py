from __future__ import annotations

from datetime import date

import pytest

from clients.constants import DocumentType
from clients.services.wezwanie_parser import (
    _detect_wezwanie_type,
    _extract_required_documents,
    _find_case_number,
    _find_fingerprints_datetime,
    _find_list_name,
    _find_ticket_number,
)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("bilet X29", "X29"),
        ("bilet: X29", "X29"),
        ("bilet nr X29", "X29"),
        ("bilet numer x29", "X29"),
        ("Bilet X29.", "X29"),
        ("some text bilet X29 more text", "X29"),
        ("bilet X29A1", "X29A1"),
        ("no bilet here", None),
    ],
)
def test_find_ticket_number_improved(text, expected):
    assert _find_ticket_number(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("numer listy Lista X1", "Lista X1"),
        ("Lista X1", "Lista X1"),
        ("Lista: X1", "Lista X1"),
        ("lista nr x1", "Lista X1"),
        ("Lista X1.", "Lista X1"),
        ("Lista A123", "Lista A123"),
        ("no list here", None),
    ],
)
def test_find_list_name_improved(text, expected):
    assert _find_list_name(text) == expected


def test_find_all_combined():
    text = "Termin numer listy Lista X1, pok. 14,16 stanowisko 10,11 Marszalkowska 3/5, bilet X29."
    assert _find_ticket_number(text) == "X29"
    assert _find_list_name(text) == "Lista X1"


def test_find_case_number_normalizes_common_mazowieckie_format():
    assert _find_case_number("numer sprawy: WSC-II-P.1234.5678") == "WSC-II-P.1234.5678"


def test_find_fingerprints_datetime_prefers_appointment_time():
    text = "Termin wizyty: 04.05.2026 godz. 10:30 w Warszawie."

    appointment_date, appointment_time = _find_fingerprints_datetime(text)

    assert appointment_date == date(2026, 5, 4)
    assert appointment_time == "10:30"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("fingerprint appointment and pobranie odciskow", "fingerprints"),
        ("termin wydania decyzji zostanie wskazany osobnym pismem", "decision"),
    ],
)
def test_detect_wezwanie_type(text, expected):
    assert _detect_wezwanie_type(text) == expected


def test_extract_required_documents_matches_core_keywords():
    found = _extract_required_documents("Nalezy dolaczyc paszport, ZUS RCA oraz potwierdzenie 340 zl.")

    assert DocumentType.PASSPORT.value in found
    assert DocumentType.ZUS_RCA_OR_INSURANCE.value in found
    assert DocumentType.PAYMENT_CONFIRMATION.value in found
