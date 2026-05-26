from datetime import date

from django.core.management import call_command

from clients.models import Client, ClientDocumentRequirement, Document, Reminder
from clients.services.custom_document_requirements import sync_custom_document_requirement_reminder


def test_custom_requirement_in_checklist_and_name_resolution(db):
    client = Client.objects.create(first_name="A", last_name="B", application_purpose="work")
    req = ClientDocumentRequirement.objects.create(client=client, name="Zaświadczenie", is_required=True)
    checklist = client.get_document_checklist()
    item = next(i for i in checklist if i.get("code") == req.document_type)
    assert item["is_custom_requirement"] is True
    assert client.get_document_name_by_code(req.document_type) == "Zaświadczenie"


def test_custom_requirement_reminder_sync_and_upload_close(db):
    client = Client.objects.create(first_name="A", last_name="B", application_purpose="work")
    req = ClientDocumentRequirement.objects.create(client=client, name="Doc", is_required=True, due_date=date(2026, 6, 1))
    sync_custom_document_requirement_reminder(req)
    reminder = Reminder.objects.get(custom_document_requirement=req)
    assert reminder.is_active is True

    Document.objects.create(client=client, document_type=req.document_type, file="documents/x.pdf")
    sync_custom_document_requirement_reminder(req)
    reminder.refresh_from_db()
    assert reminder.is_active is False


def test_update_reminders_only_custom_documents(db):
    client = Client.objects.create(first_name="A", last_name="B", application_purpose="work")
    req = ClientDocumentRequirement.objects.create(client=client, name="Doc", is_required=True, due_date=date(2026, 6, 1))
    call_command("update_reminders", "--only", "custom-documents")
    assert Reminder.objects.filter(custom_document_requirement=req, is_active=True).exists()
