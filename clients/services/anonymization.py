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

    Erasure must be *irreversible*: because the controller holds the Fernet keys,
    leaving encrypted PII in the database is not erasure — it is reversible
    pseudonymisation. So this clears/deletes every store that holds the subject's
    identifying data, not just their name:

    - Client identity (name, email, phone, passport number, birth date,
      citizenship, employer phone, free-text notes, employer link).
    - Case identifiers (authority/legacy/internal numbers, fingerprints details,
      decision text).
    - Uploaded documents: files + rows are hard-deleted.
    - PESEL and the whole MOS questionnaire (personal/passport/address/stay/
      financial/declarations), incl. PESEL-application PDFs/scans on disk.
    - Intake submissions created for the subject.
    - Email-log PII content (encrypted recipients/body/error, name-bearing
      subject) is wiped, while the non-PII audit shell (timestamp, type, status)
      is kept as proof a message was sent.

    Financial rows (payments) are intentionally retained for aggregate stats and
    accounting obligations, minus any link to identity. Idempotent: a client
    already anonymized is skipped. Returns the number of documents deleted.

    When ``mark_erasure_fulfilled`` is set, stamps ``erasure_fulfilled_at`` so a
    subject-initiated request has an auditable request → fulfilment trail.
    """
    from clients.models import Case, ClientDigitalAccess

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
    client.citizenship = ""
    client.birth_date = None
    client.passport_num = None
    client.employer_phone = ""
    client.notes = ""
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

    # PESEL national-id number lives on the digital-access record.
    ClientDigitalAccess.objects.filter(client=client).delete()

    # The MOS questionnaire is wholly the subject's encrypted personal data.
    client.mos_applications.all().delete()

    # PESEL applications carry generated PDFs / signed scans on disk.
    for pesel_app in client.pesel_applications.all():
        for file_field in (pesel_app.generated_pdf, pesel_app.signed_scan):
            if file_field:
                file_field.delete(save=False)
        pesel_app.delete()

    # Intake submissions hold the subject's encrypted personal/case data.
    client.intake_submissions.all().delete()

    # Email logs: wipe the encrypted PII payload, keep a non-PII audit shell.
    for email_log in client.email_logs.all():
        email_log.subject = "(anonymized)"
        email_log.body = ""
        email_log.recipients = ""
        email_log.error_message = ""
        email_log.save(update_fields=["subject", "body", "recipients", "error_message"])

    if mark_erasure_fulfilled:
        client.erasure_fulfilled_at = timezone.now()

    client.save()
    logger.info("Anonymized client ID %s and deleted %s documents (GDPR).", client_id, docs_deleted)
    return docs_deleted
