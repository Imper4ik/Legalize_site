from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from clients.models import Client

logger = logging.getLogger(__name__)

ANONYMIZED_PREFIX = "Anonymized"


def is_anonymized(client: Client) -> bool:
    return bool(client.first_name and client.first_name.startswith(ANONYMIZED_PREFIX))


@transaction.atomic
def anonymize_client(client: Client, *, mark_erasure_fulfilled: bool = False) -> int:
    """Irreversibly anonymize one client's PII (RODO art. 17).

    Clears client- and case-level identifying data and hard-deletes uploaded
    documents (files + rows), while leaving financial rows for aggregate stats.
    Idempotent: a client already anonymized is skipped. Returns the number of
    documents deleted.

    When ``mark_erasure_fulfilled`` is set, stamps ``erasure_fulfilled_at`` so a
    subject-initiated request has an auditable request → fulfilment trail.
    """
    from clients.models import Case

    if is_anonymized(client):
        if mark_erasure_fulfilled and client.erasure_fulfilled_at is None:
            client.erasure_fulfilled_at = timezone.now()
            client.save(update_fields=["erasure_fulfilled_at"])
        return 0

    client_id = client.id
    client.first_name = f"{ANONYMIZED_PREFIX}_{client_id}"
    client.last_name = "User"
    client.email = f"deleted_{client_id}@example.com"
    client.phone = "000000000"
    client.company = None

    for case in Case.all_objects.filter(client=client):
        case.authority_case_number = ""
        case.authority_case_number_hash = ""
        case.legacy_case_number = ""
        case.internal_number = ""
        case.fingerprints_location = ""
        case.fingerprints_ticket = ""
        case.fingerprints_list = ""
        case.fingerprints_info = ""
        case.decision = ""
        case.save(update_fields=[
            "authority_case_number", "authority_case_number_hash",
            "legacy_case_number", "internal_number",
            "fingerprints_location", "fingerprints_ticket",
            "fingerprints_list", "fingerprints_info", "decision",
        ])

    docs_deleted = 0
    for doc in client.documents.all():
        if doc.file:
            doc.file.delete(save=False)  # physical file deletion
        doc.delete(hard=True)  # database record deletion
        docs_deleted += 1

    if mark_erasure_fulfilled:
        client.erasure_fulfilled_at = timezone.now()

    client.save()
    logger.info("Anonymized client ID %s and deleted %s documents (GDPR).", client_id, docs_deleted)
    return docs_deleted
