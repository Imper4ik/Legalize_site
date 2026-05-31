"""Client case export service — generates ZIP archives with all client data."""

from __future__ import annotations

import io
import logging
import os
import zipfile
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone

from clients.services.document_helpers import document_file_exists

if TYPE_CHECKING:
    from clients.models.client import Client


logger = logging.getLogger(__name__)


class ExportSizeLimitExceeded(Exception):
    """Raised when total export file size exceeds the configured limit."""

    def __init__(self, total_mb: float, limit_mb: int):
        self.total_mb = total_mb
        self.limit_mb = limit_mb
        super().__init__(
            f"Export size {total_mb:.1f} MB exceeds limit of {limit_mb} MB"
        )


def generate_client_summary_text(client: Client) -> str:
    """Generate a plain-text summary of the client case."""

    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"CASE SUMMARY — {client.first_name} {client.last_name}")
    lines.append(f"{'=' * 60}")
    lines.append("")

    # Client info
    lines.append("CLIENT INFORMATION")
    lines.append(f"  Name:              {client.first_name} {client.last_name}")
    lines.append(f"  Email:             {client.email or '—'}")
    lines.append(f"  Phone:             {client.phone or '—'}")
    lines.append(f"  Citizenship:       {client.citizenship or '—'}")
    lines.append(f"  Application:       {client.get_application_purpose_display()}")
    lines.append(f"  Workflow Stage:    {client.get_workflow_stage_display()}")
    lines.append(f"  Case Number:       {client.case_number or '—'}")
    if hasattr(client, "fingerprints_date"):
        lines.append(f"  Fingerprints Date: {client.fingerprints_date or '—'}")
    if hasattr(client, "decision_date"):
        lines.append(f"  Decision Date:     {client.decision_date or '—'}")
    lines.append(f"  Created:           {client.created_at.strftime('%d.%m.%Y %H:%M')}")
    lines.append("")

    # Documents
    documents = client.documents.all().order_by("-uploaded_at")
    lines.append(f"DOCUMENTS ({documents.count()})")
    for doc in documents:
        status = "✓" if doc.verified else "○"
        lines.append(f"  [{status}] {doc.display_name}")
        lines.append(f"       Uploaded: {doc.uploaded_at.strftime('%d.%m.%Y %H:%M')}")
        if doc.expiry_date:
            lines.append(f"       Expires:  {doc.expiry_date}")
        if doc.ocr_status != "skipped":
            lines.append(f"       OCR:      {doc.get_ocr_status_display()}")
        if doc.ocr_name_mismatch:
            lines.append("       ⚠ Name mismatch detected by OCR")
    lines.append("")

    # Payments
    payments = client.payments.all().order_by("-created_at")
    lines.append(f"PAYMENTS ({payments.count()})")
    for payment in payments:
        lines.append(
            f"  {payment.get_service_description_display()} — "
            f"{payment.total_amount} PLN ({payment.get_status_display()})"
        )
        if payment.payment_date:
            lines.append(f"       Date: {payment.payment_date}")
    lines.append("")

    # Email history
    emails = client.email_logs.all().order_by("-sent_at")[:20]
    lines.append(f"EMAIL HISTORY (last {emails.count()})")
    for email_log in emails:
        lines.append(f"  [{email_log.sent_at.strftime('%d.%m.%Y %H:%M')}] {email_log.subject}")
        lines.append(f"       To: {email_log.recipients}")
    lines.append("")

    # Tasks
    tasks = client.staff_tasks.all().order_by("-created_at")[:20]
    lines.append(f"TASKS ({tasks.count()})")
    for task in tasks:
        status_icon = "✓" if task.status == "done" else "○"
        lines.append(f"  [{status_icon}] {task.title} ({task.get_priority_display()})")
        lines.append(f"       Assignee: {task.assignee_display}")
        if task.due_date:
            lines.append(f"       Due: {task.due_date}")
    lines.append("")

    # Reminders
    reminders = client.reminders.filter(is_active=True).order_by("due_date")
    lines.append(f"ACTIVE REMINDERS ({reminders.count()})")
    for reminder in reminders:
        lines.append(f"  [{reminder.due_date}] {reminder.display_title}")
    lines.append("")

    # Activity log (last 30)
    activities = client.activities.all().order_by("-created_at")[:30]
    lines.append(f"ACTIVITY LOG (last {activities.count()})")
    for activity in activities:
        lines.append(
            f"  [{activity.created_at.strftime('%d.%m.%Y %H:%M')}] "
            f"{activity.summary} — {activity.actor_display}"
        )
    lines.append("")
    lines.append(f"{'=' * 60}")
    lines.append(f"Generated: {timezone.now().strftime('%d.%m.%Y %H:%M')}")

    return "\n".join(lines)


def _check_export_size_limit(client: Client, max_mb: int) -> None:
    """Raise ExportSizeLimitExceeded if client files exceed *max_mb*."""
    from clients.models import DocumentVersion

    total_bytes = 0
    for doc in client.documents.all():
        if doc.file and document_file_exists(doc):
            try:
                total_bytes += doc.file.size
            except Exception as exc:
                logger.debug("Could not read document size during export sizing: document_id=%s error=%s", doc.pk, exc)

    for version in DocumentVersion.objects.filter(document__client=client):
        if version.file:
            try:
                file_name = str(version.file.name)
                if version.file.storage.exists(file_name):
                    total_bytes += version.file.size
            except Exception as exc:
                logger.debug(
                    "Could not read document version size during export sizing: version_id=%s error=%s",
                    version.pk,
                    exc,
                )

    total_mb = total_bytes / (1024 * 1024)
    if total_mb > max_mb:
        raise ExportSizeLimitExceeded(total_mb, max_mb)


def generate_client_zip(client: Client) -> io.BytesIO:
    """Create a ZIP archive containing the client summary and all documents.

    Returns an in-memory BytesIO buffer ready for streaming to the response.
    Raises ExportSizeLimitExceeded if total file sizes exceed the configured limit.
    """

    max_mb = int(getattr(settings, "MAX_TOTAL_CLIENT_EXPORT_MB", 200))
    _check_export_size_limit(client, max_mb)

    buffer = io.BytesIO()
    prefix = f"case_{client.pk}"

    missing_files_info = []

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Summary text file
        summary = generate_client_summary_text(client)
        zf.writestr(f"{prefix}/CASE_SUMMARY.txt", summary)

        # 2. All document files
        documents = client.documents.all().order_by("document_type", "-uploaded_at")
        for doc in documents:
            if not doc.file:
                continue
            if not document_file_exists(doc):
                missing_files_info.append(f"Document: ID={doc.pk}, Type={doc.document_type}")
                continue
            try:
                file_name = str(doc.file.name)
                ext = os.path.splitext(file_name)[1] or ".bin"
                archive_name = f"{prefix}/documents/document_{doc.pk}{ext}"

                # Avoid duplicate names inside the archive
                counter = 1
                base_archive_name = archive_name
                existing = {info.filename for info in zf.infolist()}
                while archive_name in existing:
                    archive_name = f"{base_archive_name[:-len(ext)]}_{counter}{ext}"
                    counter += 1

                zf.writestr(archive_name, doc.file.read())
            except Exception:
                logger.exception("Failed to add document %s to ZIP", doc.pk)

        # 3. Document versions (if any)
        from clients.models import DocumentVersion

        versions = DocumentVersion.objects.filter(
            document__client=client
        ).select_related("document").order_by("document__document_type", "-version_number")

        for version in versions:
            if not version.file:
                continue
            file_name = str(version.file.name)
            if not version.file.storage.exists(file_name):
                missing_files_info.append(f"Version: ID={version.pk}, DocID={version.document_id}, Version={version.version_number}")
                continue
            try:
                ext = os.path.splitext(file_name)[1] or ".bin"
                archive_name = f"{prefix}/document_versions/document_version_{version.pk}{ext}"
                zf.writestr(archive_name, version.file.read())
            except Exception:
                logger.exception("Failed to add version %s to ZIP", version.pk)

        # 4. Missing files report
        if missing_files_info:
            missing_report = [
                "MISSING FILES REPORT",
                "====================",
                f"The following {len(missing_files_info)} files were registered in the database but were missing from storage during export.",
                "They might have been lost if they were stored on ephemeral storage (like a local container on Railway) and the app was redeployed.",
                "",
                *missing_files_info,
                "",
                f"Report generated: {timezone.now().strftime('%d.%m.%Y %H:%M')}"
            ]
            zf.writestr(f"{prefix}/MISSING_FILES.txt", "\n".join(missing_report))
            logger.warning("ZIP export for client %s finished with %s missing files", client.pk, len(missing_files_info))


    buffer.seek(0)
    return buffer
