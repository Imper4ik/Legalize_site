# Security and RODO

## Data categories

The CRM stores client names, email, phone, citizenship, passport number, case number, notes, family links, documents, payments, reminders, OCR metadata, and email logs.

## Encryption

Sensitive model fields use Fernet-backed encrypted fields where the project already marks them as sensitive, including passport number, case number, email log body, recipients, and delivery errors. Configure:

```bash
FERNET_KEYS=current_key,previous_key
```

During rotation, prepend the new key and keep old keys until all encrypted data has been re-saved or re-encrypted. If all Fernet keys are lost, encrypted values cannot be recovered from the database.

## OCR PII policy

Background OCR must not leave PII in `Document.parsed_data`. Manual OCR review may temporarily expose parsed name/case data only to authorized staff. After confirmation or `scrub_ocr_pii`, unsafe keys are removed and `pii_scrubbed=True` is stored.

## Documents

Uploaded files are private. Views enforce staff access and client visibility checks. Downloads use safe generated filenames such as `document-123.pdf`, not original client filenames.

For Railway, do not rely on ephemeral local media. Use one of:

- `USE_DATABASE_MEDIA_STORAGE=True` for MVP simplicity;
- S3/R2/B2 with `USE_S3_MEDIA_STORAGE=True` for growth;
- Railway Volume plus explicit `ALLOW_PRODUCTION_LOCAL_MEDIA=true`.

Database backups should be copied to storage outside the application database for business use. The MVP may run with `BACKUP_REMOTE_STORAGE=false`, but that is a warning state; production operations should use the separate `backups` storage alias with S3/R2/B2 and a tested restore procedure.

## Logs and Sentry

Logging uses a PII redaction filter. Sentry is configured with `send_default_pii=False`, no request body capture, and value sanitization for sensitive keys. Avoid logging raw OCR text, email bodies, file names, passport numbers, or case numbers.

## EmailLog

EmailLog body and recipients are encrypted. Do not store raw OCR text or full uploaded documents in email logs. Delivery errors should be generic and operational.

## Audit

Critical actions are recorded through client activity logging:

- document upload;
- document delete;
- document download;
- client updates from OCR;
- OCR confirmation;
- notes changes.

For a larger commercial version, add immutable append-only audit retention and export controls.

## Data controller identity

The data controller (administrator danych) is configured in `AppSettings` and edited by the client in the UI (`/settings/templates/`), not hardcoded: legal entity name, NIP/REGON/KRS, legal address, representative, DPO/IOD contact, and the current privacy-policy version. These values are surfaced to the data subject in the consent screens (art. 13 RODO).

## Consent

Consent is recorded in the append-only `ConsentRecord` model. Each grant or withdrawal is a new immutable row capturing purpose, granted/withdrawn, policy version, channel, IP, user-agent, and timestamp, so the controller can demonstrate consent (art. 7(1)) and prove that withdrawal was as easy as granting (art. 7(3)).

Integrity is enforced in code, not just by convention:

- **Append-only**: `ConsentRecord.save()` rejects any modification of an existing row and `delete()` is blocked, so a recorded decision cannot be silently rewritten or removed.
- **Tamper-evident hash chain**: every row stores `entry_hash` — an HMAC-SHA256 (keyed by `SECRET_KEY`) over its content plus the previous row's hash for that client (`prev_hash`). Modifying, deleting, reordering, or back-dating any row breaks the chain. `ConsentRecord.verify_chain(client)` recomputes it and points at the first broken row, giving the controller demonstrable evidence for art. 7(1)/5(2) accountability. Note: because the key is `SECRET_KEY`, rotating it invalidates verification of pre-rotation rows (same trust model as the case-number hashes).

- Completing onboarding requires the data-processing consent checkbox (`clients/onboarding/declarations.html`); the required purposes are written via `clients.services.consent.record_onboarding_consent`.
- The subject manages and withdraws consent at any time in the portal at `onboarding/<token>/consent/`.
- Staff can review the consent trail read-only in Django admin (`ConsentRecordAdmin` — add/change/delete disabled).
- `ConsentRecord.is_granted(client, purpose)` is the single source of truth for the current state; marketing is opt-in and never auto-granted.

## Privacy notice

A public privacy notice (art. 13/14) is served at `/privacy/` and rendered from `clients/privacy_policy.html`. It pulls the controller identity, retention summary, policy version, and optional custom body from `AppSettings`, so publishing an updated notice is a settings edit, not a deploy. The consent screens link to it.

## Data subject rights (self-service)

The subject manages their rights from the portal:

- Access + portability (art. 15/20): `onboarding/<token>/my-data/` returns a JSON snapshot built by `clients.services.data_export.build_subject_data` (the subject's own record only, never a bulk export).
- Rectification (art. 16): existing onboarding edit steps.
- Erasure (art. 17): the subject requests deletion at `my-data/`; this stamps `Client.erasure_requested_at` and opens a high-priority `StaffTask`. Staff action the erasure out of band (archive/anonymize) — see the anonymization command below. Requests are visible/filterable in Django admin.
  - Response deadline (art. 12(3)): the CRM tracks the statutory one-month clock. While a request is pending (`erasure_requested_at` set, `erasure_fulfilled_at` empty), the client health panel and automatic checks surface a `RODO: запрос на удаление` item — a warning in the last 7 days before the deadline and a danger once it is breached — so staff act in time (`RODO_ERASURE_RESPONSE_DAYS`, `clients/models/_client_health.py`).
- Withdrawal of consent (art. 7(3)): `onboarding/<token>/consent/`.

## Records of processing (RoPA, art. 30)

Maintain a register of processing activities covering, at minimum:

- Purposes: service provision (contract), preparation of applications/documents (consent + legal obligation), optional marketing (consent).
- Categories of data subjects (clients/applicants and their family members) and data (identity, contact, citizenship, passport, case numbers, employment, uploaded documents).
- Recipients/processors (see below) and any transfers.
- Retention periods (see retention recommendations) and a general description of technical/organizational security measures (encryption, access control, audit logging).

## Processors and data processing agreements (DPA, art. 28)

Every third party that processes personal data on the controller's behalf needs a signed DPA. In this deployment that typically includes:

- Hosting/infrastructure provider (e.g. Railway).
- Object storage for media, when enabled (S3/R2/B2).
- Email delivery provider (`DEFAULT_FROM_EMAIL` transport).
- Error monitoring (Sentry) — configured with `send_default_pii=False`.

Keep a list of active processors and their DPAs alongside the RoPA.

## Breach notification (art. 33/34)

On a suspected personal-data breach:

1. Contain and assess scope (which subjects/data, likely risk).
2. Notify the supervisory authority (Prezes UODO) without undue delay, and where feasible within 72 hours of becoming aware, unless the breach is unlikely to result in a risk to data subjects.
3. Notify affected subjects when the breach is likely to result in a high risk.
4. Record every breach (facts, effects, remedial action) in an internal breach register regardless of whether notification was required.

## Retention recommendations

- Erasure (art. 17) follows an explicit approval workflow, because it is irreversible: `requested → approved → fulfilled` (or `rejected`), tracked on `Client.erasure_status` with `erasure_approved_at/by` and a decision reason. A subject request alone never destroys data — staff must review (incl. verifying the requester's identity out of band) and approve via `clients.services.erasure`. A `legal_hold` (with reason) blocks both approval and the automatic retention sweep, protecting material still needed for an active case, accounting, or legal defence. `process_erasure_requests` fulfils only `approved`, non-held clients; admin exposes approve/fulfil/hold actions.
- Erasure fulfilment is irreversible and store-complete: `anonymize_client` clears client identity (incl. passport number, birth date, citizenship, notes), scrubs and unlinks the subject's **portal login** (deactivated, password made unusable, email/username/name anonymized — internal/staff accounts are never touched), and purges PESEL (`ClientDigitalAccess`), the MOS questionnaire, PESEL applications (with their PDFs/scans on disk), intake submissions, all **documents including archived/soft-deleted ones** (`Document.all_objects`, files + rows), and email-log PII — keeping only a non-PII audit shell and financial rows for accounting. Encrypted-at-rest PII is treated as reversible (the controller holds the keys), so it is deleted rather than left encrypted. `erasure_fulfilled_at` is stamped only after `_assert_erasure_complete` verifies no PII survives; if verification fails the atomic transaction rolls back and the request stays open.
- Retention sweep (`anonymize_old_clients`) runs over `Client.all_objects`, so archived clients past retention are anonymized too rather than silently retained.
- Remove stale raw OCR PII immediately with `scrub_ocr_pii`.
- Keep email bodies only as long as needed; use `EMAIL_LOG_BODY_RETENTION_DAYS`.
- Define a client data deletion/archive policy in the service contract.
- Verify backups regularly and protect backup encryption keys separately.
