from __future__ import annotations

import ipaddress
import logging
import os
import secrets
import subprocess  # nosec B404
import time

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from clients.services.document_workflow import process_pending_document_jobs, reclaim_stale_document_jobs
from clients.services.email_campaigns import process_pending_email_campaigns
from clients.services.notifications import (
    send_appointment_notification_email,
    send_missing_documents_email,
)
from clients.services.wezwanie_parser import parse_wezwanie

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


def _authorize_cron_request(request: HttpRequest, *, action_name: str) -> JsonResponse | None:
    expected_tokens = [
        token
        for token in {
            os.environ.get("CRON_TOKEN"),
            os.environ.get("BACKUP_TRIGGER_SECRET"),
        }
        if token
    ]
    supplied_token = request.headers.get("X-CRON-TOKEN")
    authorization = request.headers.get("Authorization", "")
    if not supplied_token and authorization.startswith("Bearer "):
        supplied_token = authorization.removeprefix("Bearer ").strip()
    request_ip = _get_request_ip(request)

    if (
        not expected_tokens
        or not supplied_token
        or not any(secrets.compare_digest(supplied_token, expected_token) for expected_token in expected_tokens)
    ):
        logger.warning("Invalid CRON_TOKEN for %s from ip=%s", action_name, request_ip)
        return JsonResponse({"error": "forbidden"}, status=403)

    if not _request_ip_allowed(request):
        logger.warning("Rejected %s request from ip=%s", action_name, request_ip)
        return JsonResponse({"error": "forbidden"}, status=403)

    return None


@csrf_exempt
@require_POST
def db_backup(request: HttpRequest) -> JsonResponse:
    started_at = time.perf_counter()
    try:
        forbidden_response = _authorize_cron_request(request, action_name="database backup")
        if forbidden_response is not None:
            return forbidden_response

        request_ip = _get_request_ip(request)
        backup_result = create_db_backup()
        logger.info(
            "Database backup created: backup_id=%s ip=%s size_bytes=%s encrypted=%s plaintext_sha256=%s stored_file_sha256=%s",
            backup_result.backup_id,
            request_ip,
            backup_result.size_bytes,
            backup_result.encrypted,
            backup_result.plaintext_sha256,
            backup_result.stored_file_sha256,
        )
        return JsonResponse(
            {
                "status": "backup created",
                "backup_id": backup_result.backup_id,
                "size_bytes": backup_result.size_bytes,
                "plaintext_sha256": backup_result.plaintext_sha256,
                "stored_file_sha256": backup_result.stored_file_sha256,
                "encrypted": backup_result.encrypted,
                "ok": True,
                "command": "db_backup",
                "duration_ms": round((time.perf_counter() - started_at) * 1000),
            }
        )

    except BackupError as exc:
        logger.error("Database backup failed: %s", exc)
        return JsonResponse({"error": "backup failed"}, status=500)
    except subprocess.CalledProcessError as e:
        logger.error("pg_dump CalledProcessError: %s", e.stderr if e.stderr else str(e))
        return JsonResponse(
            {
                "error": "backup failed",
                "returncode": e.returncode,
            },
            status=500,
        )
    except Exception as e:
        logger.exception("Unexpected error during backup: %s: %s", type(e).__name__, str(e))
        return JsonResponse({"error": "backup failed"}, status=500)


@csrf_exempt
@require_POST
def process_email_campaigns_cron(request: HttpRequest) -> JsonResponse:
    started_at = time.perf_counter()
    try:
        forbidden_response = _authorize_cron_request(request, action_name="email campaign processing")
        if forbidden_response is not None:
            return forbidden_response

        limit_raw = (request.POST.get("limit") or "").strip()
        limit = int(limit_raw) if limit_raw else None
        if limit is not None:
            if limit <= 0:
                return JsonResponse({"error": "limit must be positive"}, status=400)
            if limit > 100:
                limit = 100
        results = process_pending_email_campaigns(limit=limit)
        payload = {
            "status": "processed",
            "ok": True,
            "command": "process_email_campaigns",
            "processed_count": len(results),
            "errors": [],
            "duration_ms": round((time.perf_counter() - started_at) * 1000),
            "campaigns": [
                {
                    "campaign_id": result.campaign_id,
                    "status": result.status,
                    "sent_count": result.sent_count,
                    "failed_count": result.failed_count,
                }
                for result in results
            ],
        }
        logger.info("Processed %s queued email campaign(s) via cron", len(results))
        return JsonResponse(payload)
    except ValueError:
        return JsonResponse({"error": "invalid limit"}, status=400)
    except Exception:
        logger.exception("Unexpected error during queued email campaign processing")
        return JsonResponse({"error": "email campaign processing failed"}, status=500)


@csrf_exempt
@require_POST
def process_document_jobs_cron(request: HttpRequest) -> JsonResponse:
    started_at = time.perf_counter()
    try:
        forbidden_response = _authorize_cron_request(request, action_name="document OCR jobs")
        if forbidden_response is not None:
            return forbidden_response

        limit_raw = (request.POST.get("limit") or "").strip()
        limit = None
        if limit_raw:
            limit = int(limit_raw)
            if limit <= 0:
                return JsonResponse({"error": "limit must be positive"}, status=400)
            if limit > 100:
                limit = 100

        reclaimed = reclaim_stale_document_jobs()
        results = process_pending_document_jobs(
            limit=limit,
            parser=parse_wezwanie,
            send_missing_email=send_missing_documents_email,
            send_appointment_email=send_appointment_notification_email,
        )
        errors = [
            f"job_id={result.job.id} status={result.status}"
            for result in results
            if result.status == "failed"
        ]
        logger.info("Processed %s document OCR job(s) via cron; reclaimed=%s", len(results), reclaimed)
        return JsonResponse(
            {
                "status": "processed",
                "ok": True,
                "command": "process_document_jobs",
                "processed_count": len(results),
                "errors": errors,
                "reclaimed_count": reclaimed,
                "duration_ms": round((time.perf_counter() - started_at) * 1000),
            }
        )
    except ValueError:
        return JsonResponse({"error": "invalid limit"}, status=400)
    except Exception as e:
        logger.exception("Unexpected error during document job processing")
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_POST
def update_reminders_cron(request: HttpRequest) -> JsonResponse:
    from django.core.management import call_command

    started_at = time.perf_counter()
    try:
        forbidden_response = _authorize_cron_request(request, action_name="update reminders")
        if forbidden_response is not None:
            return forbidden_response

        only_sections = request.POST.getlist("only")
        args = []
        for section in only_sections:
            args.extend(["--only", section])

        call_command("update_reminders", *args)
        logger.info("Executed update_reminders via cron")
        return JsonResponse(
            {
                "status": "processed",
                "ok": True,
                "command": "update_reminders",
                "processed_count": None,
                "errors": [],
                "duration_ms": round((time.perf_counter() - started_at) * 1000),
            }
        )
    except Exception as e:
        logger.exception("Unexpected error during update_reminders")
        return JsonResponse({"error": str(e)}, status=500)
