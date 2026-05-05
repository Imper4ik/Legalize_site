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

## Rollback Basics
- Standard Git revert: `git revert <commit>` and push.
- Monitor Railway logs carefully for migration drifts.

## Backup Restore Notes
- Backups are periodically uploaded using `db_backup.py`.
- They may be encrypted depending on `FERNET_KEYS`.
- Do not set `BACKUP_STORAGE_ALIAS` to point to `DatabaseMediaStorage`.

## Media Storage
`DatabaseMediaStorage` is acceptable for MVP and small volume file handling, but should be replaced with `USE_S3_MEDIA_STORAGE=true` (e.g., Cloudflare R2 or AWS S3) for proper production deployment handling large case files.
