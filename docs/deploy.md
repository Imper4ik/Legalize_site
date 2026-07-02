# Deploy and Architecture Guide

## Infrastructure Overview
- **Production Environment**: Railway (via Nixpacks builder)
- **Database**: PostgreSQL
- **Caching/Rate-Limiting**: Redis
- **Storage**: DatabaseMediaStorage for MVP, but should move to S3/R2 for large files.
- **Docker**: The `Dockerfile` is provided as an alternative/local option. Railway uses Nixpacks natively.

## Shell Scripts
- `release.sh`: **One-time deploy preparation.** Responsible for migrations, cache tables, and bootstrapping superuser.
- `start.sh`: **Runtime server only.** Responsible for starting gunicorn. No migrations or side effects.

## Required Environment Variables
Ensure the following variables are set in production:
- `DJANGO_SETTINGS_MODULE`
- `SECRET_KEY`
- `DATABASE_URL`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `REDIS_URL`
- `FERNET_KEYS`
- `EMAIL_*` (or provider API keys)
- `CRON_TOKEN`
- `BACKUP_TRIGGER_SECRET`
- `MAX_TOTAL_CLIENT_EXPORT_MB`
- `BACKUP_REMOTE_STORAGE` (if using external backups)

## Deploy Flow
1. Code is pushed to the target branch.
2. Railway Nixpacks builder detects Python/Django.
3. The release command (`release.sh`) applies database migrations and runs preparations.
4. The start command (`start.sh`) runs the application server (gunicorn).

## Scheduled Jobs (cron)

All background work is exposed as token-protected HTTP endpoints so any external
scheduler (Railway cron, GitHub Actions, cron-job.org, …) can drive it. Every
endpoint requires `POST` with the token in `X-CRON-TOKEN: <CRON_TOKEN>` (or
`Authorization: Bearer <CRON_TOKEN>`); optionally restrict callers with
`CRON_ALLOWED_IPS` (comma-separated IPs/CIDRs, checked against the direct peer
address).

| Endpoint | What it does | Suggested schedule |
| --- | --- | --- |
| `/cron/process-document-jobs/` | OCR queue: reclaims stale jobs, parses uploaded wezwania | every 5–15 min |
| `/cron/process-email-campaigns/` | Sends queued email campaigns | every 5–15 min |
| `/cron/update-reminders/` | Rebuilds document/payment/deadline reminders and sends notifications (`only=documents|payments|...` to scope) | daily |
| `/cron/run-maintenance/` | GDPR retention: strips email-log bodies past `EMAIL_LOG_BODY_RETENTION_DAYS`; anonymizes clients older than `ANONYMIZE_CLIENTS_AFTER_YEARS` (dry-run report unless `AUTO_ANONYMIZE_OLD_CLIENTS=True`) | daily |
| `/cron/db-backup/` | `pg_dump` backup, optionally encrypted/uploaded (also accepts legacy `BACKUP_TRIGGER_SECRET`) | daily |

Alternative without an external scheduler: run
`python manage.py run_background_automation_loop --loop` as a second Railway
service/worker. Each cycle (default 300 s) it processes OCR jobs and email
campaigns, runs the daily reminder pass (deduplicated per day inside the
command), and once per day the same retention maintenance as
`/cron/run-maintenance/`. The only job it does NOT cover is `/cron/db-backup/`,
which needs `pg_dump` and should stay on an external schedule.

Anonymization is destructive (PII overwritten, documents deleted), so it stays
a dry-run report until you explicitly set `AUTO_ANONYMIZE_OLD_CLIENTS=True`.

## Rollback Basics
- Standard Git revert: `git revert <commit>` and push.
- Monitor Railway logs carefully for migration drifts.

## Backup Restore Notes
- Backups are periodically uploaded using `db_backup.py`.
- They may be encrypted depending on `FERNET_KEYS`.
- Do not set `BACKUP_STORAGE_ALIAS` to point to `DatabaseMediaStorage`.

## Media Storage
`DatabaseMediaStorage` is acceptable for MVP and small volume file handling, but should be replaced with `USE_S3_MEDIA_STORAGE=true` (e.g., Cloudflare R2 or AWS S3) for proper production deployment handling large case files.

## Production readiness gate

Before promoting staging/preview to production, verify the runtime environment has:

- a unique `SECRET_KEY` (never the development fallback),
- explicit `FERNET_KEYS`,
- real email provider credentials (`SENDGRID_API_KEY`, `BREVO_API_KEY`, or SMTP settings),
- PostgreSQL client tools available for `pg_dump`,
- OCR binaries (`tesseract`, `pdftoppm`) if document OCR is enabled.

Recommended gate:

```bash
python manage.py check --deploy
python manage.py migrate --check
```
