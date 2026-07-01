from __future__ import annotations

from typing import Any, Iterable

from clients.models import Case, Client, MOSApplicationData, Payment


def get_case_onboarding_step(
    *,
    client: Client,
    case: Case | None,
    mos_data: MOSApplicationData | None,
    checklist: Iterable[dict[str, Any]] | None = None,
) -> int:
    """Calculate the onboarding timeline step for one selected Case.

    The client portal can expose several active cases for the same client. This
    helper deliberately scopes every signal (MOS status, checklist, payments and
    fingerprints data) to the selected case so one case cannot advance or block
    another case's onboarding UI.
    """
    status = mos_data.status if mos_data else "draft"

    if status == "draft":
        return 1
    if status == "client_filling":
        return 2

    if status in ["client_completed", "needs_correction", "staff_review"]:
        if checklist is None:
            checklist = []
        has_missing_required = any(
            item.get("is_required") and not item.get("is_uploaded") and not item.get("is_complete")
            for item in checklist
        )
        if has_missing_required:
            return 3
        return 4

    if status in ["approved_by_staff", "mos_package_ready"]:
        payment_qs = Payment.objects.filter(client=client, status__in=["pending", "partial"])
        if case is not None:
            payment_qs = payment_qs.filter(case=case)
        else:
            payment_qs = payment_qs.none()
        if payment_qs.exists():
            return 5
        return 6

    if status == "submitted_in_mos":
        return 7
    if status == "fingerprints" or (case is not None and case.fingerprints_date):
        return 8
    if status == "waiting_decision":
        return 9
    if status in ["decision_received", "closed"]:
        return 10

    return 1
