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
REDIS_URL=...  # required for atomic cross-worker rate limits
DJANGO_CACHE_TABLE=cache_table
DEFAULT_FROM_EMAIL=...
EMAIL_HOST=...
EMAIL_PORT=587
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
CRON_TOKEN=...
CRON_ALLOWED_IPS=
SENTRY_DSN=
BACKUP_REMOTE_STORAGE=True
DJANGO_ADMIN_EMAILS=alerts@example.com
ENABLE_TRANSLATION_TOOLING=True
TRANSLATION_STUDIO_STORAGE=database
TRANSLATION_DB_OVERRIDES_ENABLED=True
```

Railway may provide `RAILWAY_PUBLIC_DOMAIN` or `RAILWAY_STATIC_URL`; production settings can derive hosts and CSRF origins from those. `REDIS_URL` is mandatory because rate-limit counters must be atomic across workers. Railway deployments automatically trust platform `X-Real-IP` when Railway platform variables are present; override `TRUST_RAILWAY_CLIENT_IP` only for a verified custom topology.

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

For a full public launch, set `BACKUP_REMOTE_STORAGE=true`, keep `BACKUP_STORAGE_ALIAS=backups`, set `BACKUP_STORAGE_LOCATION=db_backups`, and configure S3/R2/B2 credentials including `AWS_STORAGE_BUCKET_NAME`. Backups must not use `DatabaseMediaStorage`.

When a Railway Volume is attached, local encrypted backups default to `$RAILWAY_VOLUME_MOUNT_PATH/db_backups` if `DB_BACKUP_DIR` is unset. This is accepted for the MVP with a production warning; external storage and a restore drill remain required before full launch.

A deploy must fail if PostgreSQL, Redis, real email delivery, persistent media, or all persistent backup storage is missing. Missing alert recipients remains a visible warning. Run `python manage.py check --deploy --fail-level ERROR` before every release.

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
