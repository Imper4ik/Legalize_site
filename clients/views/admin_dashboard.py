from __future__ import annotations

import os
from typing import Any

from django.conf import settings
from django.db.models import Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.template.defaultfilters import filesizeformat
from django.utils import timezone
from django.views import View

from clients.models import Document, DocumentProcessingJob, EmailCampaign, Reminder, StaffTask
from clients.services.roles import REPORTS_VIEW_ROLES
from clients.views.base import RoleRequiredMixin, StaffRequiredMixin
from legalize_site.runtime import runtime_dependency_summary

OCR_DEPENDENCY_KEYS = {"pytesseract", "tesseract", "pdf2image", "pdftoppm", "cv2", "numpy"}


def _email_status() -> dict[str, str]:
    backend = getattr(settings, "EMAIL_BACKEND", "")
    parts = backend.rsplit(".", 2)
    class_name = parts[-1].removesuffix("EmailBackend")
    backend_name = class_name or (parts[-2] if len(parts) > 1 else backend)
    if any(marker in backend for marker in ("console", "locmem", "dummy", "filebased")):
        return {"css": "warning", "label": f"{backend_name} (dev)"}
    return {"css": "success", "label": backend_name or "SMTP"}


def _ocr_status(missing_keys: list[str]) -> dict[str, str]:
    missing_ocr = sorted(OCR_DEPENDENCY_KEYS.intersection(missing_keys))
    if missing_ocr:
        return {"css": "warning", "label": f"Degraded ({', '.join(missing_ocr)})"}
    return {"css": "success", "label": "Ready"}


def _storage_usage() -> dict[str, Any]:
    """Cheap storage summary: DB-media aggregate when present, local walk otherwise."""
    file_count = Document.objects.exclude(file="").count()
    from database_media.models import DatabaseMediaFile

    if DatabaseMediaFile.objects.exists():
        total = DatabaseMediaFile.objects.aggregate(total=Sum("size"))["total"] or 0
        return {"total_display": filesizeformat(total), "file_count": file_count}
    media_root = str(getattr(settings, "MEDIA_ROOT", "") or "")
    if media_root and os.path.isdir(media_root) and not getattr(settings, "USE_S3_MEDIA_STORAGE", False):
        total = 0
        for dirpath, _dirnames, filenames in os.walk(media_root):
            for filename in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, filename))
                except OSError:
                    continue
        return {"total_display": filesizeformat(total), "file_count": file_count}
    return {"total_display": "—", "file_count": file_count}


class AdminDashboardView(RoleRequiredMixin, StaffRequiredMixin, View):
    allowed_roles = list(REPORTS_VIEW_ROLES)
    template_name = "clients/admin_dashboard.html"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        today = timezone.localdate()
        runtime = runtime_dependency_summary()

        active_docs = Document.objects.filter(
            client__archived_at__isnull=True,
            case__archived_at__isnull=True,
        )
        context: dict[str, Any] = {
            "generated_at": timezone.now(),
            "email_status": _email_status(),
            "ocr_status": _ocr_status(runtime["missing_keys"]),
            "storage": _storage_usage(),
            "runtime_missing_count": runtime["missing_count"],
            "runtime_dependencies": runtime["dependencies"],
            "pending_document_jobs": DocumentProcessingJob.objects.filter(
                status=DocumentProcessingJob.STATUS_PENDING
            ).count(),
            "processing_document_jobs": DocumentProcessingJob.objects.filter(
                status=DocumentProcessingJob.STATUS_PROCESSING
            ).count(),
            "failed_document_jobs": DocumentProcessingJob.objects.filter(
                status=DocumentProcessingJob.STATUS_FAILED
            ).count(),
            "pending_campaigns": EmailCampaign.objects.filter(status=EmailCampaign.STATUS_PENDING).count(),
            "running_campaigns": EmailCampaign.objects.filter(status=EmailCampaign.STATUS_RUNNING).count(),
            "failed_campaigns": EmailCampaign.objects.filter(status=EmailCampaign.STATUS_FAILED).count(),
            "docs_awaiting_confirmation": active_docs.filter(awaiting_confirmation=True).count(),
            "docs_awaiting_verification": active_docs.filter(
                file__gt="",
                verified=False,
                awaiting_confirmation=False,
                archived_at__isnull=True,
            )
            .exclude(Q(rejection_reason__isnull=False) & ~Q(rejection_reason=""))
            .exclude(expiry_date__isnull=False, expiry_date__lt=today)
            .count(),
            "overdue_tasks": StaffTask.objects.filter(
                status__in=[StaffTask.STATUS_OPEN, StaffTask.STATUS_IN_PROGRESS],
                due_date__isnull=False,
                due_date__lt=today,
                client__archived_at__isnull=True,
            ).count(),
            "docs_name_mismatch": active_docs.filter(ocr_name_mismatch=True).count(),
            "expired_documents": active_docs.filter(expiry_date__isnull=False, expiry_date__lt=today).count(),
            "active_reminders": Reminder.objects.filter(
                is_active=True,
                client__archived_at__isnull=True,
            ).count(),
            "recent_campaigns": EmailCampaign.objects.order_by("-created_at")[:5],
        }
        return render(request, self.template_name, context)
