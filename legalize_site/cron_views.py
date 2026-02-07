from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from django.core.management import call_command
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


def _env_flag(name: str, default: str = "true") -> bool:
    return os.environ.get(name, default).lower() in {"1", "true", "yes", "on"}


def _run_dumpdata_fallback(backup_path: Path) -> Path:
    json_path = backup_path.with_suffix(".json")
    with json_path.open("w", encoding="utf-8") as output_file:
        call_command("dumpdata", indent=2, stdout=output_file)
    return json_path


def _fallback_json_response(backup_path: Path, note: str) -> JsonResponse:
    json_backup_path = _run_dumpdata_fallback(backup_path)
    return JsonResponse(
        {
            "status": "backup done",
            "format": "json",
            "note": note,
            "path": str(json_backup_path),
        }
    )


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

    pg_dump_binary = os.environ.get("PG_DUMP_BINARY", "pg_dump")
    if shutil.which(pg_dump_binary) is None:
        if _env_flag("ALLOW_JSON_BACKUP_FALLBACK", "true"):
            return _fallback_json_response(backup_path, "pg_dump missing; used Django dumpdata fallback")
        return JsonResponse(
            {
                "error": "pg_dump not found in container. Install PostgreSQL client tools.",
                "binary": pg_dump_binary,
            },
            status=500,
        )

    try:
        subprocess.run(
            [pg_dump_binary, database_url, "-f", str(backup_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        if _env_flag("ALLOW_JSON_BACKUP_FALLBACK", "true"):
            return _fallback_json_response(backup_path, "pg_dump execution failed; used Django dumpdata fallback")
        return JsonResponse(
            {
                "error": "pg_dump not found in container. Install PostgreSQL client tools.",
                "binary": pg_dump_binary,
            },
            status=500,
        )
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        if _env_flag("ALLOW_JSON_BACKUP_FALLBACK", "true") and "server version mismatch" in details.lower():
            return _fallback_json_response(
                backup_path,
                "pg_dump version mismatch; used Django dumpdata fallback",
            )
        return JsonResponse(
            {
                "error": "pg_dump failed",
                "returncode": exc.returncode,
                "details": details,
            },
            status=500,
        )

    return JsonResponse({"status": "backup done", "format": "sql", "path": str(backup_path)})
