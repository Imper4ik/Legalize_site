from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction

from clients.models import (
    Client,
    Document,
    EmailLog,
    Payment,
    ClientOnboardingSession,
    ClientActivity,
    StaffAuditEvent,
    DocumentProcessingJob,
)

logger = logging.getLogger(__name__)


def delete_demo_document_files(extra_media_roots: list[str] | None = None) -> int:
    deleted_count = 0
    extra_roots = [Path(root) for root in (extra_media_roots or []) if root]
    configured_root = str(getattr(settings, "DEMO_CENTER_MEDIA_ROOT", "") or "").strip()
    if configured_root:
        extra_roots.append(Path(configured_root))

    # Also check base MEDIA_ROOT
    if settings.MEDIA_ROOT:
        extra_roots.append(Path(settings.MEDIA_ROOT))

    for document in Document.all_objects.filter(is_demo_data=True).only("id", "file"):
        file_field = document.file
        if not file_field or not file_field.name:
            continue
        file_name = file_field.name
        deleted_names: set[str] = set()
        try:
            if file_field.storage.exists(file_name):
                file_field.delete(save=False)
                deleted_names.add(file_name)
                deleted_count += 1
        except Exception as exc:
            logger.warning("Failed to delete demo file from storage: doc_id=%s error=%s", document.pk, exc)

        for root in extra_roots:
            candidate = root / file_name
            if file_name in deleted_names or not candidate.exists():
                continue
            try:
                candidate.unlink()
                deleted_names.add(file_name)
                deleted_count += 1
            except Exception as exc:
                logger.warning("Failed to unlink demo file: path=%s error=%s", candidate, exc)

    return deleted_count


def cleanup_demo_data(extra_media_roots: list[str] | None = None) -> dict[str, int]:
    report = {}
    
    # 1. Delete media files first
    files_deleted = delete_demo_document_files(extra_media_roots=extra_media_roots)
    report["files_deleted"] = files_deleted

    # 2. Hard delete database records
    with transaction.atomic():
        # DocumentProcessingJob
        dpj_count, _ = DocumentProcessingJob.objects.filter(is_demo_data=True).delete()
        report["document_processing_jobs"] = dpj_count

        # ClientActivity
        activity_count, _ = ClientActivity.objects.filter(is_demo_data=True).delete()
        report["client_activities"] = activity_count

        # StaffAuditEvent
        audit_count, _ = StaffAuditEvent.objects.filter(is_demo_data=True).delete()
        report["staff_audit_events"] = audit_count

        # ClientOnboardingSession
        session_count, _ = ClientOnboardingSession.objects.filter(is_demo_data=True).delete()
        report["onboarding_sessions"] = session_count

        # Document
        doc_count, _ = Document.all_objects.filter(is_demo_data=True).hard_delete()
        report["documents"] = doc_count

        # Payment
        payment_count, _ = Payment.all_objects.filter(is_demo_data=True).hard_delete()
        report["payments"] = payment_count

        # EmailLog
        email_count, _ = EmailLog.objects.filter(is_demo_data=True).delete()
        report["email_logs"] = email_count

        # Client
        client_count, _ = Client.all_objects.filter(is_demo_data=True).hard_delete()
        report["clients"] = client_count

    logger.info("Demo data cleanup completed: %s", report)
    return report
