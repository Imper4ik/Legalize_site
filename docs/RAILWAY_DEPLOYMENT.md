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
DEFAULT_FROM_EMAIL=...
EMAIL_HOST=...
EMAIL_PORT=587
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
CRON_TOKEN=...
CRON_ALLOWED_IPS=
USE_DATABASE_MEDIA_STORAGE=True
USE_S3_MEDIA_STORAGE=False
SENTRY_DSN=
BACKUP_REMOTE_STORAGE=
```

Railway may provide `RAILWAY_PUBLIC_DOMAIN` or `RAILWAY_STATIC_URL`; production settings can derive hosts and CSRF origins from those. `REDIS_URL` is optional: when it is absent, production rate limiting uses Django `DatabaseCache` on the PostgreSQL cache table created by `release.sh`.

## Build and release

Railway uses `nixpacks.toml`, `build.sh`, `release.sh`, and `start.sh`.

Typical sequence:

```bash
python manage.py check
python manage.py migrate --noinput
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

## Health and readiness

Use the lightweight healthcheck endpoint from the project URLs. Do not make healthchecks run OCR, migrations, or external email tests.

## Post-deploy one-time tasks

```bash
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py setup_roles
python manage.py scrub_ocr_pii --dry-run
python manage.py scrub_ocr_pii
```
