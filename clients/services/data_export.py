from __future__ import annotations

from typing import TYPE_CHECKING, Any

from clients.models import ConsentRecord

if TYPE_CHECKING:
    from clients.models import Client


def build_subject_data(client: Client) -> dict[str, Any]:
    """Assemble a data subject's own personal data for access/portability.

    Implements RODO art. 15 (access) and art. 20 (portability): a
    machine-readable snapshot of what the controller holds about the subject.
    Runs against the subject's own record only — never a bulk export.
    """
    data: dict[str, Any] = {
        "personal": {
            "first_name": client.first_name,
            "last_name": client.last_name,
            "email": client.email,
            "phone": client.phone,
            "citizenship": client.citizenship,
            "birth_date": client.birth_date.isoformat() if client.birth_date else None,
            "application_purpose": client.application_purpose,
            "language": client.language,
            "created_at": client.created_at.isoformat() if client.created_at else None,
        },
        "cases": [],
        "documents": [],
        "payments": [],
        "consents": [],
    }

    for case in client.cases.all():
        data["cases"].append(
            {
                "id": case.pk,
                "workflow_stage": getattr(case, "workflow_stage", None),
                "application_purpose": getattr(case, "application_purpose", None),
            }
        )

    for document in client.documents.all():
        data["documents"].append(
            {
                "id": document.pk,
                "document_type": document.document_type,
                "uploaded_at": document.uploaded_at.isoformat() if getattr(document, "uploaded_at", None) else None,
                "verified": getattr(document, "verified", None),
            }
        )

    for payment in client.payments.all():
        data["payments"].append(
            {
                "id": payment.pk,
                "service_description": getattr(payment, "service_description", None),
                "total_amount": str(getattr(payment, "total_amount", "")),
                "amount_paid": str(getattr(payment, "amount_paid", "")),
                "status": getattr(payment, "status", None),
            }
        )

    for consent in ConsentRecord.objects.filter(client=client).order_by("created_at"):
        data["consents"].append(
            {
                "purpose": consent.purpose,
                "granted": consent.granted,
                "policy_version": consent.policy_version,
                "channel": consent.channel,
                "created_at": consent.created_at.isoformat(),
            }
        )

    return data
