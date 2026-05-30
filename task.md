# Checklist of Audit Risk Fixes

- [x] Fix Risk A: Set default fallback of `RATE_LIMIT_CACHE_FAILURE_MODE` to `open` instead of `closed` in production settings to avoid complete DoS if Redis fails.
- [x] Fix Risk C: Improve Sentry `_sentry_before_send` helper to selectively redact sensitive keys rather than wiping the entire POST request data payload.
- [x] Fix Risk B: Write a reverse database media management command `export_database_media.py` to allow exporting all database files back to the filesystem (or target storage), providing a clear migration path away from `DatabaseMediaStorage` to S3.
