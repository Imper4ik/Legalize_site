"""Client case export service — generates ZIP archives with all client data."""

from __future__ import annotations

import io
import logging
import os
import zipfile
from datetime import date

from django.template.loader import render_to_string
from django.utils import timezone, translation

logger = logging.getLogger(__name__)


def _safe_filename(name: str) -> str:
    """Sanitize a string for use as a filename inside a ZIP archive."""
    keepchars = (" ", ".", "_", "-")
    return "".join(c for c in name if c.isalnum() or c in keepchars).strip()[:100]


def generate_client_summary_text(client) -> str:
    """Generate a plain-text summary of the client case."""

    from clients.models import DocumentRequirement

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
            lines.append(f"       ⚠ Name mismatch detected by OCR")
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
        lines.append(f"  [{reminder.due_date}] {reminder.title}")
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


def generate_client_zip(client) -> io.BytesIO:
    """Create a ZIP archive containing the client summary and all documents.

    Returns an in-memory BytesIO buffer ready for streaming to the response.
    """

    buffer = io.BytesIO()
    safe_name = _safe_filename(f"{client.first_name}_{client.last_name}")
    prefix = f"case_{safe_name}_{client.pk}"

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Summary text file
        summary = generate_client_summary_text(client)
        zf.writestr(f"{prefix}/CASE_SUMMARY.txt", summary)

        # 2. All document files
        documents = client.documents.all().order_by("document_type", "-uploaded_at")
        for doc in documents:
            if not doc.file:
                continue
            try:
                doc_name = _safe_filename(doc.display_name)
                ext = os.path.splitext(doc.file.name)[1] or ".bin"
                archive_name = f"{prefix}/documents/{doc_name}{ext}"

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
            try:
                doc_name = _safe_filename(
                    version.document.display_name if version.document else f"doc_{version.document_id}"
                )
                ext = os.path.splitext(version.file.name)[1] or ".bin"
                archive_name = f"{prefix}/document_versions/{doc_name}_v{version.version_number}{ext}"
                zf.writestr(archive_name, version.file.read())
            except Exception:
                logger.exception("Failed to add version %s to ZIP", version.pk)

    buffer.seek(0)
    return buffer
