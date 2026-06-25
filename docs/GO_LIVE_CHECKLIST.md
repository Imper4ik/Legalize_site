# Go-Live Checklist — First Clients

Status snapshot for a first-clients (pilot) launch. Verified against
`legalize_site.settings.production` with `manage.py check --deploy`.

## 1. Required environment variables

These must be set or `check --deploy` fails (by design):

| Variable | Purpose | Notes |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `legalize_site.settings.production` | |
| `APP_ENV` | `production` | |
| `DEBUG` | `False` | enforced; production refuses to boot if `True` |
| `SECRET_KEY` | strong random | the insecure fallback is rejected in production |
| `FERNET_KEYS` | comma-separated 32-byte url-safe base64 keys | required; keep old keys during rotation |
| `ALLOWED_HOSTS` | hostnames | or `RAILWAY_PUBLIC_DOMAIN` / `RAILWAY_STATIC_URL` / `RENDER_EXTERNAL_HOSTNAME` |
| `CSRF_TRUSTED_ORIGINS` | `https://…` origins | same derivation options as above |
| `DATABASE_URL` | PostgreSQL | Railway/Render provide it |
| `CRON_TOKEN` | secret for cron webhooks | constant-time checked |

### Persistent media (hard requirement)
`check --deploy` raises **E004** if production media is not persistent. Pick one:
- **MVP (recommended):** `USE_DATABASE_MEDIA_STORAGE=True` — document bytes in PostgreSQL, zero extra infra.
- **Scale:** `USE_S3_MEDIA_STORAGE=True` + AWS/R2/B2 credentials.
- **Volume:** `MEDIA_ROOT=/app/media` + `ALLOW_PRODUCTION_LOCAL_MEDIA=true` (explicit acknowledgement).

### Recommended
- `REDIS_URL` — optional; without it rate limiting uses the PostgreSQL cache table (`DJANGO_CACHE_TABLE`).
- `CRON_ALLOWED_IPS` — secondary control if the scheduler has stable IPs (advisory W009 if empty).
- `SENTRY_DSN` — error reporting (PII is scrubbed in `before_send`).
- Real email: `DEFAULT_FROM_EMAIL` (verified sender) + SendGrid/Brevo/SMTP credentials.

## 2. Deploy steps
1. `python manage.py migrate`
2. `python manage.py collectstatic --noinput`
3. `python manage.py compilemessages` — **required**: ships `.mo` files; without it PL/RU UI strings fall back to source text.
4. Create/confirm a superuser (or `DJANGO_BOOTSTRAP_SUPERUSER=auto` + `DJANGO_SUPERUSER_EMAIL/PASSWORD`).
5. `python manage.py check --deploy` — must pass with no ERRORS.
6. Smoke test: login, open dashboard, open a client, upload a document, preview/download it.

## 3. Scheduled jobs (cron webhooks)
The web service runs a built-in automation loop (`start.sh` →
`run_background_automation_loop --loop`). If you disable it
(`ENABLE_BACKGROUND_AUTOMATION_LOOP=false`), wire an external scheduler to:
- `POST /cron/process-document-jobs/` (every 5–15 min)
- `POST /cron/process-email-campaigns/` (every 5–15 min)
- `POST /cron/update-reminders/` (daily, morning)
- `POST /cron/db-backup/` (daily)

All require `Authorization: Bearer <CRON_TOKEN>`.

## 4. Safety posture (verified)
- **Encryption:** passport, case numbers, PESEL, MOS personal data are Fernet-encrypted at rest.
- **Authorization:** object access is scoped via `accessible_*_queryset` (IDOR-safe); document downloads use it.
- **Rate limiting:** auth endpoints (`account_login`, `onboarding_set_password`, resend-verification) are **fail-closed** — a cache outage cannot disable brute-force protection.
- **Autonomy / data isolation:** the autonomous reminder loop never emails Demo/Test Center records (logged as `skipped`) and `production()` excludes them from all background selections.
- **MOS 2 advisory:** the staff MOS review page warns when a case (family reunification, foreigner abroad) cannot be filed online in MOS 2.

## 5. Scope for the pilot (pobyt czasowy)
Supported purposes: **work, study, family reunification** (spouse/child/sponsor).
Not yet modelled: pobyt stały, EU long-term resident, CUKR.

## 6. Deferred (post-pilot, not launch blockers)
- **A3 — strict CSP:** drop `script-src 'unsafe-inline'`. Requires migrating 17 inline
  scripts to nonces and refactoring ~41 inline event handlers to `addEventListener`,
  with full browser verification. Current CSP is active with `unsafe-inline`; combined
  with `nh3` HTML sanitization this is acceptable for a pilot.
  **First step is available now:** set `LEGALIZE_CSP_STRICT_REPORT_ONLY=True` to emit a
  strict policy in Report-Only mode (zero UI risk) and collect the violation inventory
  from the browser console before doing the enforcing refactor.
- **B1 — MOS 2 detailed fields:** structured `karalność`, tax obligations, and the
  professional-qualifications section. Needs the official `wzór` (Dz.U. 2025 poz. 1647)
  to map fields exactly rather than guess. Core applicant/passport/family/address data
  is already captured.

## 7. Known environment-only test notes
The OCR end-to-end tests require `tesseract` + `poppler` (`pdftoppm`) and translation
tests require `gettext` (`msgfmt`) on the host. CI/production images must install these
(see `nixpacks.toml`); their absence is an environment gap, not a code defect.
