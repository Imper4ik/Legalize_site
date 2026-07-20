# Legalize_site CRM

A modern CRM built with Django for managing client applications, documents, appointments, and payments. Features automated OCR for official documents (wezwanie), an idempotent email notification system, and comprehensive tracking for ZUS and residence permits.

## Features

- **Document Management**: Upload, verify, and track document expiry. Includes S3, PostgreSQL, and local filesystem backends.
- **OCR Processing**: Automatically extract PII and application details from official letters using Tesseract OCR.
- **Workflow Automation**: Track clients through stages (New -> Document Collection -> Application Submitted -> Fingerprints -> Decision Received).
- **Automated Notifications**: Idempotent email delivery system with queueing, deduplication, and cron-based dispatch for missing/expired documents.
- **Secure by Default**: Encrypted sensitive fields (passport, case numbers), rate limiting, and robust CSRF/HSTS policies.
- **Localization**: Full translation support (PL, EN, RU).

## Deployment (Railway)

This application is ready for deployment on [Railway](https://railway.app/). 

### Quick Start
1. Provision a PostgreSQL database. Redis is optional; without `REDIS_URL`, rate limiting uses PostgreSQL `DatabaseCache`.
2. Connect the GitHub repository to a new Railway service.
3. Configure Environment Variables (see below).
4. Deploy! Railway uses `nixpacks.toml` to automatically install required system dependencies (`tesseract-ocr`, `poppler-utils`, etc.).

### Environment Variables

At a minimum, configure the following variables in Railway:
- `SECRET_KEY`: A secure random string.
- `FERNET_KEYS`: A comma-separated list of 32-byte url-safe base64-encoded keys for field encryption.
- `ALLOWED_HOSTS` & `CSRF_TRUSTED_ORIGINS`: Explicit hostnames, or allow Railway to inject `RAILWAY_PUBLIC_DOMAIN`.
- `DATABASE_URL`: Automatically provided by Railway Postgres.
- `REDIS_URL`: Optional Railway Redis URL. If omitted, production uses PostgreSQL `DatabaseCache` for rate-limiting.
- `DJANGO_CACHE_TABLE`: Optional cache table name, defaults to `cache_table`; `release.sh` creates it.
- `APP_ENV`: Set to `production`.
- `PDF_FONT_PATH`: Set to `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`.

For a full list of variables, see `.env.example`.

### Media Storage

Railway's ephemeral filesystem means uploaded files are lost on redeploy. Choose a persistent storage option:

1. **S3-Compatible (Recommended)**: AWS S3, Cloudflare R2, Backblaze B2
   - `USE_S3_MEDIA_STORAGE=True`
   - Configure `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, etc.
   
2. **PostgreSQL Database Storage (Recommended for MVP)**:
   - `USE_DATABASE_MEDIA_STORAGE=True`
   - Document metadata remains in the filesystem schema, but actual file bytes are saved to PostgreSQL.
   - Note: Database backups will grow much faster, but it requires zero additional infrastructure.

3. **Railway Volume**: Requires explicitly acknowledging the volume path
   - `MEDIA_ROOT=/app/media` (or your exact volume mount)
   - `ALLOW_PRODUCTION_LOCAL_MEDIA=true`

See `docs/deployment.md` for more details.

### Automated Tasks (Cron)

The web service starts its built-in automation loop by default. If you disable
it, configure an external scheduler (for example Railway Cron or cron-job.org)
to call the CRM's secure webhook endpoints.

Database backups can run **in-process**: set `ENABLE_INPROCESS_DB_BACKUP=true`
and the automation loop performs a full `pg_dump` once per day (retried on the
next cycle if it fails, with an admin email alert). For durable copies pair it
with `BACKUP_REMOTE_STORAGE=true` and an S3/R2/B2 `backups` alias. With this
flag the deployment needs no external scheduler at all. If you prefer an
external schedule instead, leave it off and call the webhook:

- **Database Backup**: `POST /cron/db-backup/`
- **Email Campaigns**: `POST /cron/process-email-campaigns/`
- **Background OCR**: `POST /cron/process-document-jobs/`
- **Daily Reminders**: `POST /cron/update-reminders/`
- **Retention Maintenance**: `POST /cron/retention-maintenance/` (safe to ping daily; internally weekly email-log cleanup + monthly GDPR anonymization report)

Secure these endpoints by setting `CRON_TOKEN` and passing it via the `Authorization: Bearer <TOKEN>` header. You can also restrict access by IP using `CRON_ALLOWED_IPS`.

Example using `curl`:
```bash
curl -X POST https://your-app.railway.app/cron/process-document-jobs/ \
     -H "Authorization: Bearer YOUR_CRON_TOKEN"
```

## Management Commands

The application provides several Django management commands for administration:

```bash
# Apply database migrations
python manage.py migrate

# Collect static files (done automatically during build)
python manage.py collectstatic --noinput

# Create an initial admin user
python manage.py createsuperuser

# Manually trigger background OCR processing (if not using cron)
python manage.py process_document_jobs

# Manually trigger reminders and missing document emails
python manage.py update_reminders

python manage.py scrub_ocr_pii --dry-run
python manage.py scrub_ocr_pii

# Create safe demo data for thesis defense
python manage.py seed_demo_data --confirm

# Import/Export translations
python manage.py import_po_to_db
python manage.py export_db_translations_to_po
```

## Local Development

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Setup environment variables
cp .env.example .env

# Run migrations and start the server
python manage.py migrate
python manage.py runserver
```

### Running Tests
The project uses `pytest` with extensive test coverage.
```bash
pytest
```

## Production checklist before going live

- `DJANGO_SETTINGS_MODULE=legalize_site.settings.production`
- `APP_ENV=production`
- `DEBUG=False`
- Strong `SECRET_KEY`, never the fallback value.
- Explicit `FERNET_KEYS`; keep old keys during rotation until data is re-encrypted.
- Explicit `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`, or Railway public domain envs.
- PostgreSQL `DATABASE_URL`; Redis `REDIS_URL` is optional because the app falls back to PostgreSQL cache.
- `DJANGO_CACHE_TABLE=cache_table`, unless you intentionally changed the cache table name.
- Real email credentials and verified `DEFAULT_FROM_EMAIL`.
- `CRON_TOKEN` set; `CRON_ALLOWED_IPS` configured when the scheduler has stable IPs.
- Persistent media: prefer `USE_DATABASE_MEDIA_STORAGE=True` for the MVP, or S3/R2/B2 for production growth.
- Remote backup storage configured for business use, or a documented Railway Volume/DB backup process for MVP.
- Run `python manage.py check --deploy`, migrations, `compilemessages`, `collectstatic`, and a smoke login before handover.

## Cron schedule

- `process_document_jobs`: every 5-15 minutes.
- `process_email_campaigns`: every 5-15 minutes.
- `update_reminders`: once daily in the morning.
- `db_backup`: once daily.
- `retention-maintenance`: daily ping; the command itself enforces a weekly
  email-log payload cleanup and a monthly GDPR anonymization report.
- `scrub_ocr_pii`: manually after deploy or after OCR cleanup changes.

The web service runs this automation in-process by default. `start.sh` starts
`python manage.py run_background_automation_loop --loop` when
`ENABLE_BACKGROUND_AUTOMATION_LOOP=true` (the default). Set it to `false` only
when an external scheduler or a dedicated worker runs the same jobs. The loop
processes queued OCR jobs
and queued email campaigns every 5 minutes, runs retention maintenance, and
checks missing checklist documents, missing ZUS RCA months, expiring documents, and
regular reminder records daily after 08:00 Europe/Warsaw time with a same-day retry
slot after 17:10. Missing-document and missing-ZUS RCA emails use weekly
idempotency keys per client, so they can be checked daily but are sent at most once
per week for the same reminder type. Either the loop or the external cron pings
must be configured in production — with neither, no reminders, OCR jobs, emails,
backups, or retention maintenance run at all.

Example:

```bash
curl -X POST https://your-app.railway.app/cron/process-document-jobs/ \
  -H "Authorization: Bearer $CRON_TOKEN" \
  -d "limit=50"
```

## Demo scenario for thesis defense

1. Run `python manage.py seed_demo_data --confirm`.
2. Login as `demo-staff@example.test` with the printed password.
3. Open the dashboard and show client counts, OCR awaiting review, reminders, payments, and document warnings.
4. Open a client detail page, upload a safe demo document, and show the protected preview/download flow.
5. Open the OCR awaiting review example and confirm the wezwanie fields.
6. Show generated missing documents, reminders, and EmailLog.
7. Briefly show production checks: cron token, encryption keys, persistent media, backup notes.

## More documentation

- `docs/BUSINESS_WORKFLOW.md`
- `docs/OCR_WORKFLOW.md`
- `docs/SECURITY_RODO.md`
- `docs/RAILWAY_DEPLOYMENT.md`
- `docs/TESTING.md`
- `docs/backups.md`
- `docs/TRANSLATION_AND_BUSINESS_TEXTS.md`
