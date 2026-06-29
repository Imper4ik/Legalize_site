from __future__ import annotations

from legalize_site.gunicorn_logging import redact_atoms, redact_onboarding_path


def test_redacts_token_from_request_line():
    line = "GET /ru/staff/onboarding/abc123TOKENxyz/passport/ HTTP/1.1"
    assert redact_onboarding_path(line) == "GET /ru/staff/onboarding/[redacted]/passport/ HTTP/1.1"


def test_redacts_token_at_end_of_path():
    assert redact_onboarding_path("/en/staff/onboarding/SECRET-tok_en/") == "/en/staff/onboarding/[redacted]/"


def test_redacts_token_with_query_string():
    line = "/staff/onboarding/SECRET?next=/x"
    assert redact_onboarding_path(line) == "/staff/onboarding/[redacted]?next=/x"


def test_leaves_unrelated_paths_untouched():
    assert redact_onboarding_path("GET /ru/staff/clients/42/ HTTP/1.1") == "GET /ru/staff/clients/42/ HTTP/1.1"


def test_non_string_values_pass_through():
    assert redact_onboarding_path(200) == 200
    assert redact_onboarding_path(None) is None


def test_redact_atoms_scrubs_path_atoms_only():
    data = redact_atoms(
        {
            "r": "GET /ru/staff/onboarding/SECRETTOKEN/passport/ HTTP/1.1",
            "U": "/ru/staff/onboarding/SECRETTOKEN/passport/",
            "f": "https://crm.example.com/ru/staff/onboarding/SECRETTOKEN/",
            "s": "200",
            "a": "Mozilla/5.0",
        }
    )
    assert "SECRETTOKEN" not in data["r"]
    assert "SECRETTOKEN" not in data["U"]
    assert "SECRETTOKEN" not in data["f"]
    assert "[redacted]" in data["r"]
    # Non path atoms are untouched.
    assert data["s"] == "200"
    assert data["a"] == "Mozilla/5.0"
