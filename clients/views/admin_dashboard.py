"""Admin health dashboard - global system status and metrics."""

from __future__ import annotations

import logging
import os

from django.conf import settings
from django.db.models import Count
from django.utils import timezone
from django.views.generic import TemplateView

from clients.models import (
    Client,
    Document,
    DocumentProcessingJob,
    EmailCampaign,
    Payment,
    Reminder,
    StaffTask,
)
from clients.services.roles import SETTINGS_ALLOWED_ROLES
from clients.views.base import RoleOrFeatureRequiredMixin
from legalize_site.runtime import collect_runtime_dependency_statuses

logger = logging.getLogger(__name__)


def _check_email_status() -> dict:
    """Return current email backend configuration status."""

    backend = getattr(settings, "EMAIL_BACKEND", "")
    if "console" in backend.lower():
        return {"status": "console", "label": "Console (dev)", "css": "warning"}
    if "smtp" in backend.lower() or "anymail" in backend.lower():
        host = getattr(settings, "EMAIL_HOST", "")
        password = getattr(settings, "EMAIL_HOST_PASSWORD", "")
        if host and password:
            return {"status": "configured", "label": f"SMTP ({host})", "css": "success"}
        return {"status": "incomplete", "label": "SMTP (missing credentials)", "css": "danger"}
    return {"status": "unknown", "label": backend.rsplit(".", 1)[-1], "css": "secondary"}


def _check_ocr_status() -> dict:
    """Check if Tesseract OCR is available."""

    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return {"status": "available", "label": "Tesseract OK", "css": "success"}
    except Exception:
        return {"status": "unavailable", "label": "Not installed", "css": "danger"}


def _get_storage_usage() -> dict:
    """Calculate media directory disk usage."""

    media_root = getattr(settings, "MEDIA_ROOT", "")
    if not media_root or not os.path.isdir(media_root):
        return {"total_bytes": 0, "total_display": "-", "file_count": 0}

    total_size = 0
    file_count = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(media_root):
            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(full_path)
                    file_count += 1
                except OSError:
                    pass
    except OSError:
        pass

    if total_size < 1024:
        display = f"{total_size} B"
    elif total_size < 1024**2:
        display = f"{total_size / 1024:.1f} KB"
    elif total_size < 1024**3:
        display = f"{total_size / (1024**2):.1f} MB"
    else:
        display = f"{total_size / (1024**3):.2f} GB"

    return {"total_bytes": total_size, "total_display": display, "file_count": file_count}


class AdminDashboardView(RoleOrFeatureRequiredMixin, TemplateView):
    """Global health and status dashboard for administrators."""

    template_name = "clients/admin_dashboard.html"
    allowed_roles = list(SETTINGS_ALLOWED_ROLES)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        today = now.date()

        runtime_dependencies = collect_runtime_dependency_statuses()
        runtime_missing = [item for item in runtime_dependencies if not item["available"]]

        context["email_status"] = _check_email_status()
        context["ocr_status"] = _check_ocr_status()
        context["storage"] = _get_storage_usage()
        context["is_production"] = getattr(settings, "IS_PRODUCTION", False)
        context["fernet_configured"] = getattr(settings, "FERNET_KEYS_CONFIGURED", False)
        context["runtime_dependencies"] = runtime_dependencies
        context["runtime_missing_count"] = len(runtime_missing)

        context["total_clients"] = Client.objects.count()
        context["clients_by_stage"] = list(
            Client.objects.values("workflow_stage")
            .annotate(count=Count("id"))
            .order_by("workflow_stage")
        )
        stage_display = dict(Client.WORKFLOW_STAGE_CHOICES)
        for item in context["clients_by_stage"]:
            item["display"] = stage_display.get(item["workflow_stage"], item["workflow_stage"])

        context["total_documents"] = Document.objects.count()
        context["docs_awaiting_confirmation"] = Document.objects.filter(awaiting_confirmation=True).count()
        context["docs_ocr_failed"] = Document.objects.filter(ocr_status="failed").count()
        context["docs_name_mismatch"] = Document.objects.filter(ocr_name_mismatch=True).count()

        context["pending_document_jobs"] = DocumentProcessingJob.objects.filter(
            status=DocumentProcessingJob.STATUS_PENDING
        ).count()
        context["processing_document_jobs"] = DocumentProcessingJob.objects.filter(
            status=DocumentProcessingJob.STATUS_PROCESSING
        ).count()
        context["failed_document_jobs"] = DocumentProcessingJob.objects.filter(
            status=DocumentProcessingJob.STATUS_FAILED
        ).count()
        context["retryable_document_jobs"] = DocumentProcessingJob.objects.filter(
            status=DocumentProcessingJob.STATUS_PENDING,
            attempts__gt=0,
        ).count()

        context["open_tasks"] = StaffTask.objects.filter(status__in=["open", "in_progress"]).count()
        context["overdue_tasks"] = StaffTask.objects.filter(
            status__in=["open", "in_progress"],
            due_date__lt=today,
        ).count()

        context["pending_reminders"] = Reminder.objects.filter(is_active=True, due_date__lte=today).count()
        context["upcoming_reminders"] = Reminder.objects.filter(is_active=True, due_date__gt=today).count()

        context["pending_payments"] = Payment.objects.filter(status="pending").count()
        context["total_revenue"] = sum(p.amount_paid for p in Payment.objects.filter(status="paid"))

        context["failed_campaigns"] = EmailCampaign.objects.filter(status=EmailCampaign.STATUS_FAILED).count()
        context["pending_campaigns"] = EmailCampaign.objects.filter(status=EmailCampaign.STATUS_PENDING).count()
        context["running_campaigns"] = EmailCampaign.objects.filter(status=EmailCampaign.STATUS_RUNNING).count()
        context["recent_campaigns"] = EmailCampaign.objects.order_by("-created_at")[:5]

        context["generated_at"] = now
        return context
