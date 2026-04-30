import logging

from django.db import connection
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext as _

from clients.models import DocumentProcessingJob, EmailCampaign
from legalize_site.runtime import runtime_dependency_summary
from legalize_site.utils.http import request_is_ajax

logger = logging.getLogger(__name__)


def healthcheck(request):
    try:
        connection.ensure_connection()
        db_status = "ok"
    except Exception:
        db_status = "error"

    payload = {"status": "ok", "database": db_status}

    show_details = (
        request.GET.get("details") == "1"
        and getattr(getattr(request, "user", None), "is_authenticated", False)
        and getattr(request.user, "is_staff", False)
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


def readiness(request):
    components = {}
    overall_ok = True
    show_details = (
        getattr(settings, "DEBUG", False)
        or (
            request.GET.get("details") == "1"
            and getattr(getattr(request, "user", None), "is_authenticated", False)
            and getattr(request.user, "is_staff", False)
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
        "status": runtime["status"],
        "missing_count": runtime["missing_count"],
        "missing_keys": runtime["missing_keys"],
    }

    payload = {"status": "ok" if overall_ok else "degraded"}
    if show_details:
        payload["components"] = components
    return JsonResponse(payload, status=200 if overall_ok else 503)


def csrf_failure(request, reason="", template_name="403.html"):
    is_ajax = request_is_ajax(request)
    logger.warning(
        "CSRF failure on %s %s (ajax=%s, authenticated=%s): %s",
        request.method,
        request.path,
        is_ajax,
        getattr(getattr(request, "user", None), "is_authenticated", False),
        reason,
    )

    if is_ajax:
        payload = {
            "status": "error",
            "message": _("Сессия истекла или защитный токен недействителен. Обновите страницу и повторите действие."),
            "reason": reason,
        }
        response = JsonResponse(
            payload,
            status=403,
        )
        response.json = lambda: payload
        response["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response["Pragma"] = "no-cache"
        return response

    response = render(
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
    response["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response["Pragma"] = "no-cache"
    return response
