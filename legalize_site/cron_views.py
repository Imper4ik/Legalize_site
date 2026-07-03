from __future__ import annotations

import ipaddress
import logging
import os
import secrets
import subprocess  # nosec B404
import time

from django.conf import settings
from django.core.mail import mail_admins
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from clients.models import EmailCampaign
from clients.services.document_workflow import process_pending_document_jobs, reclaim_stale_document_jobs
from clients.services.email_campaigns import process_pending_email_campaigns
from clients.services.notifications import (
    send_appointment_notification_email,
    send_missing_documents_email,
)
from clients.services.wezwanie_parser import parse_wezwanie

from .backups import BackupError, create_db_backup

logger = logging.getLogger(__name__)


def _alert_cron_failure(command: str, exc: BaseException, *, details: dict | None = None) -> None:
    logger.error(
        "Cron command failed: command=%s error_type=%s details=%s",
        command,
        type(exc).__name__,
        details or {},
    )
    try:
        from legalize_site.observability import sentry_sdk

        if sentry_sdk is not None:
            if hasattr(sentry_sdk, "push_scope"):
                with sentry_sdk.push_scope() as scope:
                    scope.set_tag("cron_command", command)
                    for key, value in (details or {}).items():
                        scope.set_extra(key, value)
                    sentry_sdk.capture_exception(exc)
            else:
                sentry_sdk.capture_exception(exc)
    except Exception:
        logger.warning("Failed to report cron failure to Sentry", exc_info=True)

    if not getattr(settings, "CRON_FAILURE_EMAIL_ALERTS", False):
        return

    try:
        mail_admins(
            subject=f"[Legalize] Cron failed: {command}",
            message=f"Command: {command}\nError type: {type(exc).__name__}\nDetails: {details or {}}",
            fail_silently=False,
        )
    except Exception:
        logger.warning("Failed to send cron failure email alert", exc_info=True)


def _get_request_ip(request: HttpRequest) -> str:
    """Return the direct peer IP for cron allowlist checks.

    Cron authentication is token-first.  The IP allowlist is only a secondary
    control and must not trust client-supplied X-Forwarded-For values.
    """

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
        _alert_cron_failure("db_backup", exc)
        return JsonResponse({"error": "backup failed"}, status=500)
    except subprocess.CalledProcessError as e:
        logger.error("pg_dump CalledProcessError: %s", e.stderr if e.stderr else str(e))
        _alert_cron_failure("db_backup", e, details={"returncode": e.returncode})
        return JsonResponse(
            {
                "error": "backup failed",
                "returncode": e.returncode,
            },
            status=500,
        )
    except Exception as e:
        logger.exception("Unexpected error during backup: %s: %s", type(e).__name__, str(e))
        _alert_cron_failure("db_backup", e)
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
        errors = [
            f"campaign_id={result.campaign_id} status={result.status} failed_count={result.failed_count}"
            for result in results
            if result.failed_count or result.status == EmailCampaign.STATUS_FAILED
        ]
        ok = not errors
        if errors:
            _alert_cron_failure(
                "process_email_campaigns",
                RuntimeError("email campaign processing completed with failed campaign(s)"),
                details={"errors": errors},
            )
        payload = {
            "status": "processed",
            "ok": ok,
            "command": "process_email_campaigns",
            "processed_count": len(results),
            "errors": errors,
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
        return JsonResponse(payload, status=200 if ok else 500)
    except ValueError:
        return JsonResponse({"error": "invalid limit"}, status=400)
    except Exception as e:
        logger.exception("Unexpected error during queued email campaign processing")
        _alert_cron_failure("process_email_campaigns", e)
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
        ok = not errors
        if errors:
            _alert_cron_failure(
                "process_document_jobs",
                RuntimeError("document OCR processing completed with failed job(s)"),
                details={"errors": errors, "reclaimed_count": reclaimed},
            )
        logger.info("Processed %s document OCR job(s) via cron; reclaimed=%s", len(results), reclaimed)
        return JsonResponse(
            {
                "status": "processed",
                "ok": ok,
                "command": "process_document_jobs",
                "processed_count": len(results),
                "errors": errors,
                "reclaimed_count": reclaimed,
                "duration_ms": round((time.perf_counter() - started_at) * 1000),
            },
            status=200 if ok else 500,
        )
    except ValueError:
        return JsonResponse({"error": "invalid limit"}, status=400)
    except Exception as e:
        logger.exception("Unexpected error during document job processing")
        _alert_cron_failure("process_document_jobs", e)
        return JsonResponse({"error": "document job processing failed"}, status=500)


@csrf_exempt
@require_POST
def retention_maintenance_cron(request: HttpRequest) -> JsonResponse:
    """Run guarded retention maintenance.

    The command performs weekly email-payload cleanup and a monthly
    anonymization report. Actual client anonymization remains a separate,
    explicitly confirmed operator action.
    """
    from django.core.management import call_command

    started_at = time.perf_counter()
    try:
        forbidden_response = _authorize_cron_request(request, action_name="retention maintenance")
        if forbidden_response is not None:
            return forbidden_response

        call_command("run_retention_maintenance")
        logger.info("Executed run_retention_maintenance via cron")
        return JsonResponse(
            {
                "status": "processed",
                "ok": True,
                "command": "run_retention_maintenance",
                "processed_count": None,
                "errors": [],
                "duration_ms": round((time.perf_counter() - started_at) * 1000),
            }
        )
    except Exception as e:
        logger.exception("Unexpected error during retention maintenance")
        _alert_cron_failure("run_retention_maintenance", e)
        return JsonResponse({"error": "retention maintenance failed"}, status=500)


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
        _alert_cron_failure("update_reminders", e)
        return JsonResponse({"error": "update reminders failed"}, status=500)
