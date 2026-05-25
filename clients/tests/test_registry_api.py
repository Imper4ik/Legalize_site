from __future__ import annotations

from unittest.mock import Mock, patch

from clients.services.registry_api import match_names, query_ceidg_stub, query_krs, verify_employer


def _krs_api_payload() -> dict:
    return {
        "odpis": {
            "dane": {
                "dzial1": {
                    "danePodmiotu": {
                        "nazwa": "GOOGLE POLAND SP. Z O.O.",
                        "identyfikatory": {
                            "nip": "5252344078",
                            "regon": "015706447",
                        },
                    }
                },
                "dzial2": {
                    "reprezentacja": {
                        "sklad": [
                            {
                                "imiona": {"imie": "Anna", "imieDrugie": "Maria"},
                                "nazwisko": {"nazwiskoICzlon": "Kowalska"},
                            }
                        ]
                    },
                    "prokurenci": [
                        {
                            "imiona": {"imie": "Piotr", "imieDrugie": "Tomasz"},
                            "nazwisko": {"nazwiskoICzlon": "Miller"},
                        }
                    ],
                },
            }
        }
    }


def _krs_registry_result() -> dict:
    return {
        "source": "KRS",
        "company_name": "GOOGLE POLAND SP. Z O.O.",
        "is_active": True,
        "nip": "5252344078",
        "regon": "015706447",
        "representatives": ["Anna Maria Kowalska", "Piotr Tomasz Miller"],
        "error": None,
    }


def test_match_names():
    reps = ["Micha\u0142 Nowak", "Anna Maria Kowalska"]

    assert match_names(["Michal Nowak"], reps) == "Micha\u0142 Nowak"
    assert match_names(["anna kowalska"], reps) == "Anna Maria Kowalska"
    assert match_names(["Nowak Michal"], reps) == "Micha\u0142 Nowak"
    assert match_names(["Kowalska Anna Maria"], reps) == "Anna Maria Kowalska"

    masked_reps = ["M******* M***** M***********", "P*** T****** M******"]

    assert match_names(["Menachem Mendel Misinkiewicz"], masked_reps) == "M******* M***** M***********"
    assert match_names(["Menachem Misinkiewicz"], masked_reps) == "M******* M***** M***********"
    assert match_names(["Menahem Miskiewicz"], masked_reps) == "M******* M***** M***********"
    assert match_names(["Piotr Tomasz Miller"], masked_reps) == "P*** T****** M******"
    assert match_names(["Mariusz Mazur"], masked_reps) is None
    assert match_names(["Jan Kowalski"], reps) is None


@patch("clients.services.registry_api.requests.get")
def test_query_krs_parses_api_payload(get_mock):
    response = Mock()
    response.status_code = 200
    response.json.return_value = _krs_api_payload()
    get_mock.return_value = response

    result = query_krs("0000240611")

    assert result["error"] is None
    assert "GOOGLE POLAND" in result["company_name"].upper()
    assert result["nip"] == "5252344078"
    assert result["regon"] == "015706447"
    assert result["is_active"] is True
    assert result["representatives"] == ["Anna Maria Kowalska", "Piotr Tomasz Miller"]
    called_url = get_mock.call_args[0][0]
    assert "0000240611" in called_url
    assert get_mock.call_args.kwargs["timeout"] == 10


def test_query_ceidg_stub():
    result = query_ceidg_stub("5252344078")
    assert result["error"] is None
    assert result["is_active"] is True
    assert "Jan Kowalski" in result["representatives"]

    result_invalid = query_ceidg_stub("1234567890")
    assert result_invalid["error"] is not None
    assert result_invalid["is_active"] is False


@patch("clients.services.registry_api.query_krs")
def test_verify_employer_krs_success(query_krs_mock):
    query_krs_mock.return_value = _krs_registry_result()
    rep_name = "Anna Maria Kowalska"

    report = verify_employer(krs="0000240611", detected_names=[rep_name, "Random Name"])

    assert report["is_employer_active"] is True
    assert report["company_name"] == "GOOGLE POLAND SP. Z O.O."
    assert report["signer_authorized"] is True
    assert report["matched_signer"] == rep_name
    assert not any("Signer not found" in w for w in report["warnings"])


@patch("clients.services.registry_api.query_krs")
def test_verify_employer_krs_no_match(query_krs_mock):
    query_krs_mock.return_value = _krs_registry_result()

    report = verify_employer(krs="0000240611", detected_names=["Jan Kowalski", "Random Person"])

    assert report["is_employer_active"] is True
    assert report["signer_authorized"] is False
    assert any("Signer not found in authorized representatives list" in w for w in report["warnings"])
