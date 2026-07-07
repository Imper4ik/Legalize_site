from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from clients.models import Client

logger = logging.getLogger(__name__)

ANONYMIZED_PREFIX = "Anonymized"


class ErasureIncompleteError(RuntimeError):
    """Raised when PII survives an erasure run, so it must not be marked fulfilled."""


def is_anonymized(client: Client) -> bool:
    return bool(client.first_name and client.first_name.startswith(ANONYMIZED_PREFIX))


def _anonymize_portal_user(client: Client) -> None:
    """Neutralise the subject's portal login without touching internal accounts.

    A data subject's own portal account is part of their personal data, so on
    erasure it must be deactivated, made unusable, and stripped of the email /
    technical-username / name that identify them, then unlinked from the client.
    Staff, superusers, and internal accounts are never modified.
    """
    user = client.user
    if user is None:
        return
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        # Never scrub an internal/staff account (spec: erasure targets the subject).
        return

    user.is_active = False
    user.set_unusable_password()
    # Both email and the derived technical username leak the original address.
    user.email = f"deleted_user_{client.id}@example.invalid"
    user.username = f"deleted-user-{client.id}"
    user.first_name = ""
    user.last_name = ""
    user.save(update_fields=["is_active", "password", "email", "username", "first_name", "last_name"])

    client.user = None


def _purge_subject_stores(client: Client) -> int:
    """Delete/clear every store that holds the subject's PII. Idempotent.

    Returns the number of document rows deleted.
    """
    from clients.models import Case, ClientDigitalAccess, Document

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

    # Documents: use all_objects so archived/soft-deleted rows and their files are
    # removed too — otherwise archived scans would survive the erasure.
    docs_deleted = 0
    for doc in Document.all_objects.filter(client=client):
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

    # Email logs: wipe the encrypted PII payload, keep a non-PII audit shell
    # (timestamp, type, status) for accountability. Payments are retained for
    # accounting, minus identity, which lives on the (now anonymized) client.
    for email_log in client.email_logs.all():
        email_log.subject = "(anonymized)"
        email_log.body = ""
        email_log.recipients = ""
        email_log.error_message = ""
        email_log.save(update_fields=["subject", "body", "recipients", "error_message"])

    return docs_deleted


def _assert_erasure_complete(client: Client) -> None:
    """Raise ErasureIncompleteError if any PII store still holds the subject's data.

    This gates ``erasure_fulfilled_at`` so a request is never marked fulfilled
    while recoverable PII remains.
    """
    from clients.models import ClientDigitalAccess, Document

    problems: list[str] = []
    if Document.all_objects.filter(client=client).exists():
        problems.append("documents")
    if ClientDigitalAccess.objects.filter(client=client).exists():
        problems.append("digital_access")
    if client.mos_applications.exists():
        problems.append("mos_applications")
    if client.pesel_applications.exists():
        problems.append("pesel_applications")
    if client.intake_submissions.exists():
        problems.append("intake_submissions")
    # EmailLog body/recipients are Fernet-encrypted, so they cannot be filtered by
    # value in SQL; decrypt in Python (few rows per client) to confirm the wipe.
    if any((log.body or "") or (log.recipients or "") for log in client.email_logs.all()):
        problems.append("email_logs")
    # A still-linked, non-staff portal account means the login was not scrubbed.
    user = client.user
    if user is not None and not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
        problems.append("portal_user")

    if problems:
        raise ErasureIncompleteError(
            f"Erasure incomplete for client {client.id}; PII remains in: {', '.join(problems)}"
        )


@transaction.atomic
def anonymize_client(client: Client, *, mark_erasure_fulfilled: bool = False) -> int:
    """Irreversibly anonymize one client's PII (RODO art. 17).

    Erasure must be *irreversible*: because the controller holds the Fernet keys,
    leaving encrypted PII in the database is not erasure — it is reversible
    pseudonymisation. So this clears/deletes every store that holds the subject's
    identifying data, not just their name:

    - Client identity (name, email, phone, passport number, birth date,
      citizenship, employer phone, free-text notes, employer link).
    - The portal login account (deactivated, password made unusable, email /
      username / name anonymized, unlinked) — internal/staff accounts untouched.
    - Case identifiers (authority/legacy/internal numbers, fingerprints details,
      decision text).
    - Uploaded documents, **including archived/soft-deleted ones**: files + rows
      are hard-deleted via ``Document.all_objects``.
    - PESEL and the whole MOS questionnaire, incl. PESEL-application PDFs/scans.
    - Intake submissions created for the subject.
    - Email-log PII content is wiped, keeping a non-PII audit shell.

    Financial rows (payments) are intentionally retained for accounting, minus
    any link to identity. The whole operation is atomic and idempotent.

    ``erasure_fulfilled_at`` is stamped only after :func:`_assert_erasure_complete`
    confirms no PII survives; if verification fails the transaction rolls back and
    the request stays open. Returns the number of documents deleted.
    """
    already = is_anonymized(client)

    docs_deleted = _purge_subject_stores(client)
    _anonymize_portal_user(client)

    if not already:
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

    if mark_erasure_fulfilled:
        # Only mark fulfilled once we have verified nothing recoverable remains.
        _assert_erasure_complete(client)
        if client.erasure_fulfilled_at is None:
            client.erasure_fulfilled_at = timezone.now()
        from clients.models import Client as ClientModel
        client.erasure_status = ClientModel.ErasureStatus.FULFILLED

    client.save()
    logger.info("Anonymized client ID %s and deleted %s documents (GDPR).", client.id, docs_deleted)
    return docs_deleted
