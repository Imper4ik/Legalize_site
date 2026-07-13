# Go-Live Checklist — First Clients

Status snapshot for a first-clients (pilot) launch. Verify the release with
`legalize_site.settings.production` and `python manage.py check --deploy`.

## 1. Required environment variables

These must be set or production boot/system checks fail by design:

| Variable | Purpose | Notes |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `legalize_site.settings.production` | |
| `APP_ENV` | `production` | |
| `DEBUG` | `False` | production refuses to boot if `True` |
| `SECRET_KEY` | strong random value | insecure fallback is rejected |
| `FERNET_KEYS` | comma-separated 32-byte URL-safe base64 keys | retain old keys during rotation |
| `ALLOWED_HOSTS` | hostnames | can be derived from Railway/Render variables |
| `CSRF_TRUSTED_ORIGINS` | `https://…` origins | can be derived from Railway/Render variables |
| `DATABASE_URL` | PostgreSQL connection | Railway/Render can provide it |
| `CRON_TOKEN` | primary secret for cron webhooks | required for every non-backup cron endpoint |

`BACKUP_TRIGGER_SECRET` is a legacy compatibility token accepted by
`/cron/db-backup/` only. It must never authorize OCR, email, reminder, or
retention jobs.

### Persistent media (hard requirement)

`check --deploy` raises **E004** if production media is not persistent. Pick one:

- **MVP:** `USE_DATABASE_MEDIA_STORAGE=True` — document bytes in PostgreSQL.
- **Scale:** `USE_S3_MEDIA_STORAGE=True` plus AWS/R2/B2 credentials.
- **Volume:** `MEDIA_ROOT=/app/media` plus
  `ALLOW_PRODUCTION_LOCAL_MEDIA=true` as an explicit acknowledgement.

### Required before real-client pilot

- Real email provider and verified sender: `DEFAULT_FROM_EMAIL` plus
  SendGrid/Brevo/SMTP credentials; verify SPF, DKIM, and DMARC on the sending domain.
- Remote backup storage: `BACKUP_REMOTE_STORAGE=true` plus a dedicated external
  `STORAGES` backend. A failed upload must fail the cron request and trigger alerts.
- Complete tenant/controller data seeded through `TENANT_*` variables or the admin UI.
- Exactly one automation contour: external cron is recommended; the in-process
  automation loop is opt-in with `ENABLE_BACKGROUND_AUTOMATION_LOOP=true`.

### Recommended

- `REDIS_URL`; without it rate limiting uses the PostgreSQL cache table.
- `CRON_ALLOWED_IPS` when the scheduler has stable source IPs.
- `SENTRY_DSN` for error reporting; PII is scrubbed before events are sent.

## 2. Deploy steps

1. Run `./release.sh` before starting the web process. It performs migration
   preparation, payment-integrity audit, migrations, tenant configuration, cache
   table creation, and optional translation import.
2. Run `python manage.py collectstatic --noinput` and
   `python manage.py compilemessages` during the build.
3. Run `python manage.py check --deploy` with the production settings profile.
4. Create/confirm a superuser through the controlled bootstrap flow if needed.
5. Verify `/readyz/`: database and the configured production cache must both work.
6. Smoke-test login, dashboard, client access, upload, OCR review, email delivery,
   cron authentication, persistent media, and alert delivery.

Render uses `preDeployCommand: ./release.sh` and `/readyz/` as its health check.
`start.sh` retains an idempotent migration/cache fallback for platforms whose
release phase is not guaranteed.

## 3. Scheduled jobs

The in-process scheduler is disabled by default. When using an external scheduler:

- `POST /cron/process-document-jobs/` every 5–15 minutes;
- `POST /cron/process-email-campaigns/` every 5–15 minutes;
- `POST /cron/update-reminders/` daily;
- `POST /cron/run-maintenance/` daily;
- `POST /cron/db-backup/` daily.

Send `Authorization: Bearer <CRON_TOKEN>` for all endpoints. The backup endpoint
also accepts the isolated legacy backup token during migration away from it.
Never enable the in-process loop and external versions of the same jobs together.

## 4. Safety posture already implemented

- Passport data, case numbers, PESEL, MOS personal data, OCR payloads, and email
  payloads are Fernet-encrypted at rest.
- Object access is scoped through permission-aware querysets; document downloads
  follow the same isolation rules.
- Critical authentication/public flows use fail-closed rate limiting.
- Production readiness fails with HTTP 503 when the configured cache is unavailable.
- Remote backup upload is fail-closed rather than reporting a false success.
- Audit metadata preserves approved workflow/status/document/payment identifiers
  while rejecting non-whitelisted PII.
- The autonomous jobs exclude Demo/Test Center data from production selections.

## 5. Mandatory go-live gates still requiring operational input

- Enrol all staff/admin accounts in MFA and approve the recovery/support procedure.
- Complete and legally review `/privacy/`, DPA records, RoPA, retention schedule,
  DPIA threshold assessment, and breach-response runbook.
- Execute and record a backup → environment deletion → restore drill from external storage.
- Verify production OCR, email delivery, cron execution, persistent media, and alerts.
- Add malware scanning/quarantine, or keep public uploads disabled and restrict
  uploads to trusted staff until scanning is available.

## 6. Pilot scope

Supported temporary-residence purposes: **work, study, and family reunification**.
Not yet modelled: permanent residence, EU long-term resident, and CUKR.

## 7. Deferred after the controlled pilot

- Remove remaining `style-src 'unsafe-inline'` usage after a CSP report-only inventory.
- Add the remaining detailed MOS fields from the authoritative current form.
- Add realistic authenticated load testing, JS unit tests, and a full WCAG/axe pass.
- Decide between automated per-firm instance provisioning and shared multi-tenancy,
  then add SaaS billing, SLA/support, and formal tenant offboarding.

## 8. Environment-only test notes

OCR end-to-end tests require Tesseract and Poppler; translation tests require
gettext. CI and production images install these dependencies through the platform
build configuration. A production smoke test is still required because package
presence alone does not prove OCR, backup, email, and storage integration.
