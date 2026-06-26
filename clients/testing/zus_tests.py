from __future__ import annotations

from datetime import date

from clients.constants import DocumentType
from clients.models import Case, Client
from clients.services.cases import resolve_single_active_case
from clients.services.zus import missing_zus_months
from clients.testing.assertions import RelatedObjects, ScenarioRecorder
from clients.testing.factories import create_test_client, create_test_document


def _case_of(client: Client) -> Case:
    """Resolve the client's single active case (ZUS state lives on the Case, §4)."""
    case = resolve_single_active_case(client)
    assert case is not None
    return case


def _zus_client(email: str) -> Client:
    client = create_test_client(
        email=email,
        first_name="Zus",
        last_name="Client",
        purpose="work",
        workflow_stage="waiting_decision",
    )
    # Process dates live on the Case now (spec §4).
    case = resolve_single_active_case(client)
    assert case is not None
    case.fingerprints_date = date(2026, 2, 10)
    case.save(update_fields=["fingerprints_date"])
    return client


def run_zus_scenarios(recorder: ScenarioRecorder) -> None:
    today = date(2026, 5, 15)
    expected_missing = [date(2026, 3, 1), date(2026, 4, 1)]

    missing_client = _zus_client("client_missing_zus@example.test")
    missing = missing_zus_months(_case_of(missing_client), today=today)
    recorder.check(
        "zus.missing_zus_months_detected",
        missing == expected_missing,
        expected=expected_missing,
        actual=missing,
        related=RelatedObjects(client=missing_client),
    )

    good_client = _zus_client("client_zus_good@example.test")
    create_test_document(
        good_client,
        doc_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
        verified=True,
        zus_period_month=date(2026, 3, 1),
        filename="zus-march.pdf",
    )
    create_test_document(
        good_client,
        doc_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
        verified=True,
        zus_period_month=date(2026, 4, 1),
        filename="zus-april.pdf",
    )
    recorder.check(
        "zus.approved_zus_rca_closes_missing_problem",
        missing_zus_months(_case_of(good_client), today=today) == [],
        expected=[],
        actual=missing_zus_months(_case_of(good_client), today=today),
        related=RelatedObjects(client=good_client),
    )

    wrong_month_client = _zus_client("client_wrong_zus_month@example.test")
    create_test_document(
        wrong_month_client,
        doc_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
        verified=True,
        zus_period_month=date(2026, 1, 1),
        filename="zus-wrong-month.pdf",
    )
    wrong_month_missing = missing_zus_months(_case_of(wrong_month_client), today=today)
    recorder.check(
        "zus.wrong_month_does_not_close_expected_periods",
        wrong_month_missing == expected_missing,
        expected=expected_missing,
        actual=wrong_month_missing,
        related=RelatedObjects(client=wrong_month_client),
    )

    insurance_client = _zus_client("client_insurance_satisfies_zus@example.test")
    insurance_doc = create_test_document(
        insurance_client,
        doc_type=DocumentType.HEALTH_INSURANCE.value,
        verified=True,
        expiry_date=date(2026, 5, 31),
        filename="insurance.pdf",
    )
    insurance_missing = missing_zus_months(_case_of(insurance_client), today=today)
    recorder.check(
        "zus.insurance_satisfies_zus_rca_requirement",
        insurance_missing == [],
        expected=[],
        actual=insurance_missing,
        error_message="Health insurance should satisfy ZUS RCA requirements.",
        related=RelatedObjects(client=insurance_client, document=insurance_doc),
    )

