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

## Retention recommendations

- Remove stale raw OCR PII immediately with `scrub_ocr_pii`.
- Keep email bodies only as long as needed; use `EMAIL_LOG_BODY_RETENTION_DAYS`.
- Define a client data deletion/archive policy in the service contract.
- Verify backups regularly and protect backup encryption keys separately.
