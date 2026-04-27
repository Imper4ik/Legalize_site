[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Deployment

## Mandatory Environment Variables

For production, you must set the `PDF_FONT_PATH` variable with the absolute path to a TrueType/OpenType font file that will be used for PDF generation (e.g., `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`).

## Production Hardening Variables

Set `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` explicitly. Railway deployments may also provide `RAILWAY_PUBLIC_DOMAIN` and `RAILWAY_STATIC_URL`; Render deployments may provide `RENDER_EXTERNAL_HOSTNAME`. The app derives host and CSRF entries from these platform variables, but it no longer ships with a hardcoded Railway hostname.

Set `REDIS_URL` in production so rate limiting uses Django `RedisCache` across workers. Without `REDIS_URL`, Django falls back to local cache and a system check warning is emitted.

Default HSTS production values are `SECURE_HSTS_SECONDS=31536000`, `SECURE_HSTS_INCLUDE_SUBDOMAINS=False`, and `SECURE_HSTS_PRELOAD=False`. Override them via env only after confirming the domain policy. Do not enable preload until the domain is ready for browser preload submission.

Sentry tracing is controlled by `SENTRY_TRACES_SAMPLE_RATE`; use `0.1` for normal production traffic unless active debugging requires a temporary increase.

## Backups

Instructions for enabling and restoring backups on Railway can be found in the document: [docs/backups.md](backups.md).

---

# Polski <a name="polski"></a>

# Wdrażanie (Deployment)

## Obowiązkowe Zmienne Środowiskowe

Dla środowiska produkcyjnego należy ustawić zmienną `PDF_FONT_PATH` z bezwzględną ścieżką do pliku czcionki TrueType/OpenType, który będzie używany do generowania plików PDF (np. `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`).

## Kopie Zapasowe

Instrukcja włączania i przywracania kopii zapasowych na Railway znajduje się w dokumencie: [docs/backups.md](backups.md).

---

# Русский <a name="русский"></a>

# Развертывание (Deployment)

## Обязательные переменные окружения

Для продакшена необходимо задать переменную `PDF_FONT_PATH` с абсолютным путём к файлу шрифта TrueType/OpenType, который будет использоваться для генерации PDF (например, `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`).

## Бэкапы

Инструкция по включению и восстановлению бэкапов на Railway находится в документе: [docs/backups.md](backups.md).


## Railway media storage safety

For production, **do not** rely on ephemeral container filesystem for client documents.

Use one of:

1. S3-compatible storage (AWS S3 / Cloudflare R2 / Backblaze B2) with `USE_S3_MEDIA_STORAGE=true`;
2. Railway Volume mounted to media/backup directories.

Security requirements:

- Media files must not be publicly exposed by direct bucket listing.
- Document downloads should go through protected Django views with access checks.
- If production runs with local media and no explicit acknowledgement (`ALLOW_PRODUCTION_LOCAL_MEDIA=true`), project system checks emit a warning.
