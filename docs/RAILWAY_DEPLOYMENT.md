# Railway Deployment

## Required environment

```bash
DJANGO_SETTINGS_MODULE=legalize_site.settings.production
APP_ENV=production
DEBUG=False
SECRET_KEY=...
FERNET_KEYS=...
ALLOWED_HOSTS=your-app.railway.app
CSRF_TRUSTED_ORIGINS=https://your-app.railway.app
DATABASE_URL=...
REDIS_URL=...  # optional; PostgreSQL DatabaseCache is used when omitted
DJANGO_CACHE_TABLE=cache_table
DEFAULT_FROM_EMAIL=...
EMAIL_HOST=...
EMAIL_PORT=587
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
CRON_TOKEN=...
CRON_ALLOWED_IPS=
SENTRY_DSN=
BACKUP_REMOTE_STORAGE=
ENABLE_TRANSLATION_TOOLING=True
TRANSLATION_STUDIO_STORAGE=database
TRANSLATION_DB_OVERRIDES_ENABLED=True
```

Railway may provide `RAILWAY_PUBLIC_DOMAIN` or `RAILWAY_STATIC_URL`; production settings can derive hosts and CSRF origins from those. `REDIS_URL` is optional: when it is absent, production rate limiting uses Django `DatabaseCache` on the PostgreSQL cache table named by `DJANGO_CACHE_TABLE` (default `cache_table`). `release.sh` runs `python manage.py createcachetable`, so the table is created during release.

## Build and release

Railway uses `nixpacks.toml`, `build.sh`, `release.sh`, and `start.sh`.

Typical sequence:

```bash
python manage.py check
python manage.py migrate --noinput
python manage.py createcachetable
python manage.py compilemessages --ignore "venv" --ignore ".venv"
python manage.py collectstatic --noinput
gunicorn legalize_site.wsgi:application
```

Create the initial admin after deploy:

```bash
python manage.py createsuperuser
python manage.py setup_roles
```

## Cron

Use Railway Cron if available in your plan, or an external scheduler such as cron-job.org. Send the token as either header:

```bash
Authorization: Bearer $CRON_TOKEN
X-CRON-TOKEN: $CRON_TOKEN
```

Recommended schedule:

- `/cron/process-document-jobs/`, POST `limit=50`, every 5-15 minutes.
- `/cron/process-email-campaigns/`, POST `limit=50`, every 5-15 minutes.
- `/cron/update-reminders/`, POST daily in the morning.
- `/cron/db-backup/`, POST daily.

Cron JSON includes `ok`, `command`, `processed_count` where available, `errors`, and `duration_ms`.

## Media

For a Railway MVP, prefer:

```bash
USE_DATABASE_MEDIA_STORAGE=True
```

For production growth, use S3/R2/B2 and set the S3-compatible variables. A Railway Volume is also acceptable if `MEDIA_ROOT` points to the mounted volume and `ALLOW_PRODUCTION_LOCAL_MEDIA=true` documents that choice.

## Backups

Run daily DB backups and verify restore with `python manage.py test_restore`. If media is in PostgreSQL, DB backups include files. If media is local or S3, backup media separately.

For a thesis/MVP deployment, `BACKUP_REMOTE_STORAGE=false` is allowed and emits a warning rather than an error. For real business use, set `BACKUP_REMOTE_STORAGE=true`, keep `BACKUP_STORAGE_ALIAS=backups`, set `BACKUP_STORAGE_LOCATION=db_backups`, and configure S3/R2/B2 credentials including `AWS_STORAGE_BUCKET_NAME`. Backups must not use `DatabaseMediaStorage`.

Expected `check --deploy` warnings for MVP are limited to Django's standard HTTPS/HSTS reminders if you intentionally changed those settings and the project warning that remote backup storage is not enabled. Media storage and cache misconfiguration should be treated as errors.

## Health and readiness

Use the lightweight healthcheck endpoint from the project URLs. Do not make healthchecks run OCR, migrations, or external email tests.

## Post-deploy one-time tasks

```bash
python manage.py migrate --noinput
python manage.py createcachetable
python manage.py compilemessages --ignore "venv" --ignore ".venv"
python manage.py collectstatic --noinput
python manage.py scrub_ocr_pii --dry-run
python manage.py scrub_ocr_pii
```

## Translations
After first deploy, if you want to populate the DB with translations from PO files, run:
```bash
python manage.py import_po_to_db
```
See [TRANSLATION_AND_BUSINESS_TEXTS.md](TRANSLATION_AND_BUSINESS_TEXTS.md) for more details.
