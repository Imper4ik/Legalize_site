from __future__ import annotations

import ipaddress
import logging
import os
import subprocess

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_POST

from .backups import BackupError, create_db_backup

logger = logging.getLogger(__name__)


def _get_request_ip(request: HttpRequest) -> str:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return (request.META.get("REMOTE_ADDR") or "").strip()


def _request_ip_allowed(request: HttpRequest) -> bool:
    allowed_values = [item.strip() for item in os.environ.get("CRON_ALLOWED_IPS", "").split(",") if item.strip()]
    if not allowed_values:
        return True

    request_ip = _get_request_ip(request)
    try:
        client_ip = ipaddress.ip_address(request_ip)
    except ValueError:
        return False

    for allowed_value in allowed_values:
        try:
            if client_ip in ipaddress.ip_network(allowed_value, strict=False):
                return True
        except ValueError:
            if request_ip == allowed_value:
                return True
    return False


@require_POST
def db_backup(request: HttpRequest) -> JsonResponse:
    try:
        expected_token = os.environ.get("CRON_TOKEN")
        supplied_token = request.headers.get("X-CRON-TOKEN")
        request_ip = _get_request_ip(request)

        if not expected_token or supplied_token != expected_token:
            logger.warning("Invalid CRON_TOKEN supplied from ip=%s", request_ip)
            return JsonResponse({"error": "forbidden"}, status=403)
        if not _request_ip_allowed(request):
            logger.warning("Rejected database backup request from ip=%s", request_ip)
            return JsonResponse({"error": "forbidden"}, status=403)

        backup_result = create_db_backup()
        logger.info(
            "Database backup created: backup_id=%s ip=%s size_bytes=%s encrypted=%s sha256=%s",
            backup_result.backup_id,
            request_ip,
            backup_result.size_bytes,
            backup_result.encrypted,
            backup_result.sha256,
        )
        return JsonResponse({
            "status": "backup created",
            "backup_id": backup_result.backup_id,
            "size_bytes": backup_result.size_bytes,
            "sha256": backup_result.sha256,
            "encrypted": backup_result.encrypted,
        })

    except BackupError as exc:
        logger.error("Database backup failed: %s", exc)
        return JsonResponse({"error": str(exc)}, status=500)
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
