# Graceful Degradation Policy

This document defines how the Legalize site application behaves when external
services or runtime dependencies become unavailable.

## Principles

1. **Never lose user data** — uploads, form submissions, and client records must
   be persisted even when downstream services fail.
2. **Degrade visibly** — when a feature falls back, log a warning and show a
   user-facing message where appropriate.
3. **Fail hard only in production startup** — missing secrets and encryption keys
   cause the application to refuse to start (see `settings/base.py` guards).
   Runtime failures are handled gracefully.

---

## Service Degradation Matrix

| Dependency | Unavailable Behavior | User Impact | Alerting |
|---|---|---|---|
| **OCR (Tesseract)** | Document uploads succeed; parsing is skipped. `manual_review_required` flag set on document. | Staff sees "requires manual review" badge. | `logger.exception()` on parse failure. |
| **Email (SMTP / API)** | `SafeSMTPEmailBackend` catches transport errors. In dev, `EMAIL_FALLBACK_TO_CONSOLE` prints to logs. In prod, error is logged and user sees "email failed" message. | Notification emails not delivered; staff sees error toast. | `logger.exception()` + Sentry event. |
| **Database backup (pg_dump)** | Backup endpoint returns HTTP 500 with error detail. App continues running normally. | No backup created; cron alerting should catch the failure. | `logger.error()` + JSON error response. |
| **Translation compilation (msgfmt)** | Falls back to pure-Python `.po` → `.mo` compiler. If that also fails, untranslated strings surface. | Some UI strings may appear in source language. | `logger.warning()` per file. |
| **PDF fonts** | PDF export uses fallback system font or skips rendering. | PDF reports may have missing glyphs. | `logger.warning()` at PDF generation time. |
| **Exchange rate API** | Calculator uses hardcoded fallback rates with a visible disclaimer. | Rates may be stale; user sees warning banner. | `logger.warning()` when API is unreachable. |
| **Fernet encryption (cryptography)** | Backup encryption skipped if library is missing. PII fields require the library — app will error on model access. | Backups stored unencrypted (plaintext still auto-deleted). | `logger.warning()` for backup; model-level error for PII. |

---

## Mass Email

Mass email is dispatched in a background thread via `EmailCampaign` model.
Individual send failures are recorded per-recipient in `EmailCampaign.error_details`.
The campaign completes with status `FAILED` if any recipient could not be reached,
allowing staff to review and retry.

---

## Startup Guards (Hard Failures)

These are intentional `ImproperlyConfigured` exceptions that prevent the
application from starting in an unsafe state:

| Check | Environment | Behavior |
|---|---|---|
| `SECRET_KEY` is default fallback | Production | `raise ImproperlyConfigured` |
| `FERNET_KEYS` not set | Production | `raise ImproperlyConfigured` |

Additionally, Django system checks (`legalize_site.W003`, `legalize_site.W004`)
surface warnings in development when these keys use derived/default values.

---

## Adding New Dependencies

When integrating a new external service:

1. Wrap the call in a `try/except` and log the exception.
2. Decide: is this service **critical** (user data loss) or **enhancement** (convenience)?
   - Critical → retry queue or fail the operation with a clear error message.
   - Enhancement → skip gracefully, set a flag, show a soft warning.
3. Add the service to the matrix above.
4. Add a Django system check if the service requires environment configuration.
