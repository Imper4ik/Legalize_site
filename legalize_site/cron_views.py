from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


@csrf_exempt
@require_http_methods(["GET", "POST"])
def db_backup(request: HttpRequest) -> JsonResponse:
    expected_token = os.environ.get("CRON_TOKEN")
    supplied_token = request.headers.get("X-CRON-TOKEN")

    if expected_token and supplied_token != expected_token:
        return JsonResponse({"error": "forbidden"}, status=403)

    database_url = os.environ.get("DATABASE_URL") or os.environ.get("RAILWAY_DATABASE_URL")
    if not database_url:
        return JsonResponse({"error": "DATABASE_URL is not configured"}, status=500)

    backup_dir = Path(os.environ.get("DB_BACKUP_DIR", "/tmp"))
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_name = f"backup-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.sql"
    backup_path = backup_dir / backup_name

    subprocess.run(
        ["pg_dump", database_url, "-f", str(backup_path)],
        check=True,
    )

    return JsonResponse({"status": "backup done", "path": str(backup_path)})
