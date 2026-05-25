from __future__ import annotations

import pytest
from clients.services.registry_api import match_names, query_krs, query_ceidg_stub, verify_employer

def test_match_names():
    # Accent normalization and case-insensitive
    reps = ["Michał Nowak", "Anna Maria Kowalska"]
    
    assert match_names(["Michal Nowak"], reps) == "Michał Nowak"
    assert match_names(["anna kowalska"], reps) == "Anna Maria Kowalska"
    assert match_names(["Nowak Michal"], reps) == "Michał Nowak"
    assert match_names(["Kowalska Anna Maria"], reps) == "Anna Maria Kowalska"
    
    # Masked names matching
    masked_reps = ["M******* M***** M***********", "P*** T****** M******"]
    
    # Perfect match with correct name (Menachem Mendel Misinkiewicz -> 8, 6, 12 chars)
    assert match_names(["Menachem Mendel Misinkiewicz"], masked_reps) == "M******* M***** M***********"
    
    # Match omitting middle name (First & Last match)
    assert match_names(["Menachem Misinkiewicz"], masked_reps) == "M******* M***** M***********"
    
    # Match with minor OCR spelling error (Menahem Miskiewicz -> 7, 10 chars vs 8, 12 chars)
    assert match_names(["Menahem Miskiewicz"], masked_reps) == "M******* M***** M***********"
    
    # Exact match for another masked name (Piotr Tomasz Miller -> 5, 7, 6 chars)
    assert match_names(["Piotr Tomasz Miller"], masked_reps) == "P*** T****** M******"
    
    # Non-matching due to length discrepancy (Mariusz Mazur -> 7, 5 chars)
    assert match_names(["Mariusz Mazur"], masked_reps) is None
    
    # Non-matching
    assert match_names(["Jan Kowalski"], reps) is None


def test_query_krs_live():
    # Google Poland Sp. z o.o.
    krs = "0000240611"
    result = query_krs(krs)
    
    assert result["error"] is None
    assert result["company_name"] is not None
    assert "GOOGLE POLAND" in result["company_name"].upper()
    assert result["nip"] == "5252344078"
    assert result["is_active"] is True
    # Verify that at least one representative is fetched (e.g. contains board members/prokurator)
    assert len(result["representatives"]) > 0


def test_query_ceidg_stub():
    # Valid NIP (Google Poland NIP is valid)
    result = query_ceidg_stub("5252344078")
    assert result["error"] is None
    assert result["is_active"] is True
    assert "Jan Kowalski" in result["representatives"]

    # Invalid NIP
    result_invalid = query_ceidg_stub("1234567890")
    assert result_invalid["error"] is not None
    assert result_invalid["is_active"] is False


def test_verify_employer_krs_success():
    # Verify using KRS and list of detected names containing the actual representatives (scrubbed, but they are in the result)
    krs = "0000240611"
    krs_data = query_krs(krs)
    
    # We will pick one of the actual representatives fetched
    rep_name = krs_data["representatives"][0]
    
    # Test verify_employer matches the representative
    report = verify_employer(krs=krs, detected_names=[rep_name, "Random Name"])
    
    assert report["is_employer_active"] is True
    assert report["company_name"] is not None
    assert report["signer_authorized"] is True
    assert report["matched_signer"] == rep_name
    assert not any("Signer not found" in w for w in report["warnings"])


def test_verify_employer_krs_no_match():
    # Verify using KRS but with no matching representative
    krs = "0000240611"
    report = verify_employer(krs=krs, detected_names=["Jan Kowalski", "Random Person"])
    
    assert report["is_employer_active"] is True
    assert report["signer_authorized"] is False
    assert any("Signer not found in authorized representatives list" in w for w in report["warnings"])
