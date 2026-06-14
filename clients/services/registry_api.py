import logging
import re
import unicodedata
from typing import Any

import requests

logger = logging.getLogger(__name__)

def normalize_string(s: str) -> str:
    """Lowercase, strip, and remove Polish accents/diacritics."""
    if not s:
        return ""
    s = s.strip().lower()
    # Manual replace for Polish L with stroke since NFD doesn't strip it
    s = s.replace("ł", "l").replace("Ł", "l")
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9\s\*]", "", s)


def _is_masked_word_match(ocr_word: str, rep_word: str) -> bool:
    """Check if an OCR word matches a masked representative word."""
    if not ocr_word or not rep_word:
        return False
    # If the representative word is not masked, do a direct comparison
    if "*" not in rep_word:
        return ocr_word == rep_word

    # Representative word is masked (e.g., "m*******")
    # First letter must match
    if ocr_word[0] != rep_word[0]:
        return False

    # Length must be close (tolerance: +/-1 for short words, +/-2 for longer words)
    max_diff = 1 if len(rep_word) < 8 else 2
    if abs(len(ocr_word) - len(rep_word)) > max_diff:
        return False

    # Check any other non-asterisk characters if they exist in the mask
    for c_ocr, c_rep in zip(ocr_word, rep_word):
        if c_rep != "*" and c_ocr != c_rep:
            return False

    return True


def _match_masked_name(ocr_name: str, rep_name: str) -> bool:
    """Compare a full OCR name with a masked representative name."""
    ocr_words = normalize_string(ocr_name).split()
    rep_words = normalize_string(rep_name).split()

    # Filter out short words like middle initials or prepositions
    ocr_words = [w for w in ocr_words if len(w) > 1]
    rep_words = [w for w in rep_words if len(w) > 1]

    if len(ocr_words) < 2 or len(rep_words) < 2:
        return False

    # Check standard order: First Name matches First Word, Last Name matches Last Word
    if _is_masked_word_match(ocr_words[0], rep_words[0]) and _is_masked_word_match(ocr_words[-1], rep_words[-1]):
        return True

    # Check reversed order: Last Name matches First Word, First Name matches Last Word
    if _is_masked_word_match(ocr_words[-1], rep_words[0]) and _is_masked_word_match(ocr_words[0], rep_words[-1]):
        return True

    return False


def match_names(ocr_names: list[str], representative_names: list[str]) -> str | None:
    """
    Match OCR names with representative names from KRS/CEIDG.
    Returns the matching representative name if found, else None.
    """
    if not ocr_names or not representative_names:
        return None

    norm_reps = [normalize_string(r) for r in representative_names]

    for ocr_name in ocr_names:
        norm_ocr = normalize_string(ocr_name)

        # 1. Direct match (if unmasked)
        if norm_ocr in norm_reps:
            idx = norm_reps.index(norm_ocr)
            return representative_names[idx]

        # 2. Word subset check (handles middle names or reverse order, if unmasked)
        ocr_words = set(norm_ocr.split())
        if len(ocr_words) >= 2:
            for rep_name, n_rep in zip(representative_names, norm_reps):
                rep_words = set(n_rep.split())
                if len(rep_words) >= 2:
                    if ocr_words.issubset(rep_words) or rep_words.issubset(ocr_words):
                        return rep_name

        # 3. Masked name matching (if representative names contain asterisks)
        for rep_name in representative_names:
            if "*" in rep_name:
                if _match_masked_name(ocr_name, rep_name):
                    return rep_name

    return None


def query_krs(krs_number: str) -> dict[str, Any]:
    """
    Query the official Polish KRS API.
    Returns a dictionary with name, active status, representatives, and raw data.
    """
    # Normalize KRS: 10 digits
    krs_clean = re.sub(r"[^\d]", "", krs_number).zfill(10)
    url = f"https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/{krs_clean}?rejestr=P&format=json"

    result: dict[str, Any] = {
        "source": "KRS",
        "company_name": None,
        "is_active": False,
        "nip": None,
        "regon": None,
        "representatives": [],
        "error": None
    }

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            odpis = data.get("odpis", {})
            dane = odpis.get("dane", {})

            # Extract basic info
            dane_podmiotu = dane.get("dzial1", {}).get("danePodmiotu", {})
            result["company_name"] = dane_podmiotu.get("nazwa")
            result["is_active"] = True # If returned, it's generally active unless wykreślony is specified

            idents = dane_podmiotu.get("identyfikatory", {})
            result["nip"] = idents.get("nip")
            result["regon"] = idents.get("regon")

            # Parse representatives (Dział 2 - Zarząd & Prokurenci)
            reps = []

            # Board (Zarząd)
            reprezentacja = dane.get("dzial2", {}).get("reprezentacja", {})
            sklad = reprezentacja.get("sklad", [])
            for member in sklad:
                imie = member.get("imiona", {}).get("imie", "")
                imie2 = member.get("imiona", {}).get("imieDrugie", "")
                nazwisko = member.get("nazwisko", {}).get("nazwiskoICzlon", "")

                full_name = f"{imie} {nazwisko}" if not imie2 else f"{imie} {imie2} {nazwisko}"
                reps.append(full_name.strip())

            # Prokurenci
            prokurenci = dane.get("dzial2", {}).get("prokurenci", [])
            for prok in prokurenci:
                imie = prok.get("imiona", {}).get("imie", "")
                imie2 = prok.get("imiona", {}).get("imieDrugie", "")
                nazwisko = prok.get("nazwisko", {}).get("nazwiskoICzlon", "")

                full_name = f"{imie} {nazwisko}" if not imie2 else f"{imie} {imie2} {nazwisko}"
                reps.append(full_name.strip())

            result["representatives"] = sorted(list(set(reps)))

        elif response.status_code == 204:
            result["error"] = "Company not found in KRS registry (204)."
        else:
            result["error"] = f"KRS API returned status code {response.status_code}."

    except requests.RequestException as e:
        logger.warning("Error querying KRS API for %s: %s", krs_number, e)
        result["error"] = f"KRS API request failed: {str(e)}"

    return result


def query_ceidg_stub(nip: str) -> dict[str, Any]:
    """
    Stub for CEIDG API query.
    Always returns mock success with active status and a placeholder representative name if NIP is valid.
    """
    from clients.services.company_parser import validate_nip

    result: dict[str, Any] = {
        "source": "CEIDG",
        "company_name": None,
        "is_active": False,
        "nip": nip,
        "regon": None,
        "representatives": [],
        "error": None
    }

    if validate_nip(nip):
        result["company_name"] = f"CEIDG MOCK COMPANY (NIP: {nip})"
        result["is_active"] = True
        # Mock representative name
        result["representatives"] = ["Jan Kowalski"]
    else:
        result["error"] = "Invalid NIP format."

    return result


def verify_employer(
    nip: str | None = None,
    krs: str | None = None,
    detected_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Verify employer against Polish registries (KRS or CEIDG stub).
    Matches detected_names against representatives.
    """
    report: dict[str, Any] = {
        "registry_source": None,
        "company_name": None,
        "is_employer_active": False,
        "nip": nip,
        "krs": krs,
        "representatives": [],
        "signer_authorized": False,
        "matched_signer": None,
        "warnings": []
    }

    registry_data: dict[str, Any] | None = None

    # 1. Query KRS if KRS number is detected
    if krs:
        registry_data = query_krs(krs)
        if registry_data.get("error"):
            report["warnings"].append(f"KRS query failed: {registry_data['error']}")

    # 2. Query CEIDG stub if no KRS but NIP is detected
    elif nip:
        registry_data = query_ceidg_stub(nip)
        if registry_data.get("error"):
            report["warnings"].append(f"CEIDG query failed: {registry_data['error']}")

    if registry_data and not registry_data.get("error") and registry_data.get("is_active"):
        report["registry_source"] = registry_data["source"]
        report["company_name"] = registry_data["company_name"]
        report["is_employer_active"] = registry_data["is_active"]
        report["representatives"] = registry_data["representatives"]
        if registry_data.get("nip"):
            report["nip"] = registry_data["nip"]
        if registry_data.get("krs"):
            report["krs"] = registry_data["krs"]

        # Match names
        if detected_names and registry_data["representatives"]:
            matched = match_names(detected_names, registry_data["representatives"])
            if matched:
                report["signer_authorized"] = True
                report["matched_signer"] = matched
            else:
                report["warnings"].append("Signer not found in authorized representatives list.")
        else:
            report["warnings"].append("No signature name detected in document or no representatives found.")
    else:
        if not report["warnings"]:
            report["warnings"].append("Employer could not be verified in any registry.")

    return report
