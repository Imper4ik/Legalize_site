from __future__ import annotations

import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def db_backup(request: HttpRequest) -> JsonResponse:
    try:
        expected_token = os.environ.get("CRON_TOKEN")
        supplied_token = request.headers.get("X-CRON-TOKEN")

        if not expected_token or supplied_token != expected_token:
            logger.warning("Invalid CRON_TOKEN supplied")
            return JsonResponse({"error": "forbidden"}, status=403)

        # Check if pg_dump is available
        pg_dump_path = shutil.which("pg_dump")
        if not pg_dump_path:
            error_msg = "pg_dump command not found in system PATH"
            logger.error(error_msg)
            return JsonResponse({"error": error_msg}, status=500)

        database_url = os.environ.get("DATABASE_URL") or os.environ.get("RAILWAY_DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL is not configured")
            return JsonResponse({"error": "DATABASE_URL is not configured"}, status=500)

        # Fix DATABASE_URL scheme: pg_dump requires 'postgresql://' not 'postgres://'
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
            logger.info("Normalized DATABASE_URL scheme to postgresql://")

        backup_dir = Path(os.environ.get("DB_BACKUP_DIR", "/tmp"))
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_name = f"backup-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.sql"
        backup_path = backup_dir / backup_name

        logger.info(f"Starting database backup to {backup_path} using {pg_dump_path}")

        # Run pg_dump with the corrected DATABASE_URL
        result = subprocess.run(
            [pg_dump_path, database_url, "-f", str(backup_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        
        logger.info(f"Database backup completed successfully: {backup_path}")
        return JsonResponse({
            "status": "backup done",
            "path": str(backup_path),
            "size_bytes": backup_path.stat().st_size if backup_path.exists() else 0,
        })
        
    except subprocess.CalledProcessError as e:
        error_msg = f"pg_dump failed: {e.stderr if e.stderr else str(e)}"
        logger.error(f"pg_dump CalledProcessError: {error_msg}")
        return JsonResponse({
            "error": error_msg,
            "returncode": e.returncode,
        }, status=500)
    except Exception as e:
        error_msg = f"Unexpected error during backup: {type(e).__name__}: {str(e)}"
        logger.exception(error_msg)
        return JsonResponse({
            "error": error_msg,
        }, status=500)
