from __future__ import annotations

from clients.models import ClientDocumentRequirement, Document, Reminder


def requirement_has_uploaded_document(requirement: ClientDocumentRequirement) -> bool:
    return Document.objects.filter(
        client=requirement.client,
        document_type=requirement.document_type,
        archived_at__isnull=True,
    ).exists()


def sync_custom_document_requirement_reminder(requirement: ClientDocumentRequirement, *, dry_run: bool = False) -> str:
    reminders_qs = Reminder.objects.filter(custom_document_requirement=requirement, is_active=True)
    if not requirement.is_active or not requirement.is_required or not requirement.due_date or requirement_has_uploaded_document(requirement):
        if dry_run:
            return "would_deactivate" if reminders_qs.exists() else "noop"
        changed = reminders_qs.update(is_active=False)
        return "deactivated" if changed else "noop"

    defaults = {
        "client": requirement.client,
        "reminder_type": "document",
        "title": f"Нужно предоставить документ: {requirement.name}",
        "notes": requirement.description,
        "due_date": requirement.due_date,
        "is_active": True,
        "document": None,
    }
    if dry_run:
        return "would_upsert"
    Reminder.objects.update_or_create(custom_document_requirement=requirement, defaults=defaults)
    return "upserted"
