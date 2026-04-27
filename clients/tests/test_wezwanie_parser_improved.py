import pytest
from clients.services.wezwanie_parser import _find_ticket_number, _find_list_name

@pytest.mark.parametrize("text, expected", [
    ("bilet X29", "X29"),
    ("bilet: X29", "X29"),
    ("bilet nr X29", "X29"),
    ("bilet numer x29", "X29"),
    ("Bilet X29.", "X29"),
    ("some text bilet X29 more text", "X29"),
    ("bilet X29A1", "X29A1"),
    ("no bilet here", None),
])
def test_find_ticket_number_improved(text, expected):
    assert _find_ticket_number(text) == expected

@pytest.mark.parametrize("text, expected", [
    ("numer listy Lista X1", "Lista X1"),
    ("Lista X1", "Lista X1"),
    ("Lista: X1", "Lista X1"),
    ("lista nr x1", "Lista X1"),
    ("Lista X1.", "Lista X1"),
    ("Lista A123", "Lista A123"),
    ("no list here", None),
])
def test_find_list_name_improved(text, expected):
    assert _find_list_name(text) == expected

def test_find_all_combined():
    text = "Termin ... numer listy Lista X1, pok. 14,16 stanowisko 10,11 Marszałkowska 3/5 w Warszawie, bilet X29."
    assert _find_ticket_number(text) == "X29"
    assert _find_list_name(text) == "Lista X1"
