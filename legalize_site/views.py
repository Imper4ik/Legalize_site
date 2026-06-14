from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext as _

from clients.models import DocumentProcessingJob, EmailCampaign
from legalize_site.runtime import runtime_dependency_summary
from legalize_site.utils.http import request_is_ajax

logger = logging.getLogger(__name__)


class InspectableJsonResponse(JsonResponse):
    def json(self) -> Any:
        return json.loads(self.content.decode(self.charset))


def healthcheck(request: HttpRequest) -> HttpResponse:
    try:
        connection.ensure_connection()
        db_status = "ok"
    except Exception:
        db_status = "error"

    payload: dict[str, Any] = {"status": "ok", "database": db_status}

    user = getattr(request, "user", None)
    show_details = (
        request.GET.get("details") == "1"
        and user and getattr(user, "is_authenticated", False)
        and getattr(user, "is_staff", False)
    )
    if show_details:
        payload["queues"] = {
            "pending_document_jobs": DocumentProcessingJob.objects.filter(status="pending").count(),
            "retryable_document_jobs": DocumentProcessingJob.objects.filter(status="pending", attempts__gt=0).count(),
            "failed_document_jobs": DocumentProcessingJob.objects.filter(status="failed").count(),
            "pending_email_campaigns": EmailCampaign.objects.filter(status=EmailCampaign.STATUS_PENDING).count(),
            "running_email_campaigns": EmailCampaign.objects.filter(status=EmailCampaign.STATUS_RUNNING).count(),
            "failed_email_campaigns": EmailCampaign.objects.filter(status=EmailCampaign.STATUS_FAILED).count(),
        }
        payload["runtime"] = runtime_dependency_summary()

    return JsonResponse(payload, status=200 if db_status == "ok" else 503)


def readiness(request: HttpRequest) -> HttpResponse:
    components: dict[str, Any] = {}
    overall_ok = True
    user = getattr(request, "user", None)
    show_details = (
        getattr(settings, "DEBUG", False)
        or (
            request.GET.get("details") == "1"
            and user and getattr(user, "is_authenticated", False)
            and getattr(user, "is_staff", False)
        )
    )

    try:
        connection.ensure_connection()
        components["database"] = {"status": "ok"}
    except Exception as exc:
        overall_ok = False
        logger.exception("Readiness database check failed")
        components["database"] = {"status": "error", "error": exc.__class__.__name__}

    cache_required = bool(getattr(settings, "REDIS_URL", ""))
    try:
        cache_key = "readiness:cache"
        cache.set(cache_key, "ok", timeout=30)
        cache_ok = cache.get(cache_key) == "ok"
        components["cache"] = {
            "status": "ok" if cache_ok else "error",
            "required": cache_required,
            "backend": settings.CACHES["default"]["BACKEND"],
        }
        if cache_required and not cache_ok:
            overall_ok = False
    except Exception as exc:
        logger.exception("Readiness cache check failed")
        components["cache"] = {
            "status": "error",
            "required": cache_required,
            "backend": settings.CACHES["default"]["BACKEND"],
            "error": exc.__class__.__name__,
        }
        if cache_required:
            overall_ok = False

    runtime = runtime_dependency_summary()
    components["runtime"] = {
        "status": str(runtime["status"]),
        "missing_count": int(runtime["missing_count"]),
        "missing_keys": list(runtime["missing_keys"]),
    }

    payload: dict[str, Any] = {"status": "ok" if overall_ok else "degraded"}
    if show_details:
        payload["components"] = components
    return JsonResponse(payload, status=200 if overall_ok else 503)


def csrf_failure(request: HttpRequest, reason: str = "", template_name: str = "403.html") -> HttpResponse:
    is_ajax = request_is_ajax(request)
    user = getattr(request, "user", None)
    logger.warning(
        "CSRF failure on %s %s (ajax=%s, authenticated=%s): %s",
        request.method,
        request.path,
        is_ajax,
        user and getattr(user, "is_authenticated", False),
        reason,
    )

    if is_ajax:
        payload = {
            "status": "error",
            "message": str(_("Сессия истекла или защитный токен недействителен. Обновите страницу и повторите действие.")),
            "reason": reason,
        }
        json_response = InspectableJsonResponse(
            payload,
            status=403,
        )
        json_response["Cache-Control"] = "no-store, no-cache, must-revalidate"
        json_response["Pragma"] = "no-cache"
        return json_response

    html_response = render(
        request,
        template_name,
        {
            "error_title": _("Ошибка безопасности"),
            "error_message": _(
                "Сессия истекла или защитный токен недействителен. Обновите страницу и повторите действие."
            ),
            "support_email": "support@legalize.pl",
        },
        status=403,
    )
    html_response["Cache-Control"] = "no-store, no-cache, must-revalidate"
    html_response["Pragma"] = "no-cache"
    return html_response
