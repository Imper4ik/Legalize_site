from __future__ import annotations

from datetime import date, timedelta

from django.core.management import call_command

from clients.constants import DocumentType
from clients.models import Client, Document, EmailLog, Payment, Reminder, StaffTask


def test_with_health_stats_uses_distinct_counts(db):
    client = Client.objects.create(first_name="A", last_name="B", application_purpose="work")
    today = date(2026, 5, 26)

    Document.objects.create(
        client=client,
        document_type=DocumentType.PASSPORT.value,
        expiry_date=today - timedelta(days=1),
        file="documents/a.pdf",
    )
    Document.objects.create(
        client=client,
        document_type=DocumentType.HEALTH_INSURANCE.value,
        expiry_date=today + timedelta(days=1),
        file="documents/b.pdf",
    )

    EmailLog.objects.create(client=client, subject="s1", body="b1", recipients="a@b.c", template_type="appointment_notification")
    EmailLog.objects.create(client=client, subject="s2", body="b2", recipients="a@b.c", template_type="appointment_notification")

    Payment.objects.create(client=client, service_description="consultation", total_amount="100.00", amount_paid="0.00", status="pending", due_date=today)
    Payment.objects.create(client=client, service_description="consultation", total_amount="100.00", amount_paid="10.00", status="partial", due_date=today)

    StaffTask.objects.create(client=client, title="t1", due_date=today - timedelta(days=1), status="open")
    StaffTask.objects.create(client=client, title="t2", due_date=today - timedelta(days=1), status="in_progress")

    stats = (
        Client.objects.filter(pk=client.pk)
        .with_health_stats(today=today)
        .values(
            "health_expired_documents_count",
            "health_expiring_documents_count",
            "health_appointment_email_sent_count",
            "health_overdue_payments_count",
            "health_overdue_tasks_count",
        )
        .get()
    )

    assert stats["health_expired_documents_count"] == 1
    assert stats["health_expiring_documents_count"] == 1
    assert stats["health_appointment_email_sent_count"] == 2
    assert stats["health_overdue_payments_count"] == 2
    assert stats["health_overdue_tasks_count"] == 2


def test_legal_stay_choice_and_no_duplicate_reminders(db):
    client = Client.objects.create(first_name="L", last_name="S", application_purpose="work")
    mos_data = client.mos_application_data
    mos_data.legal_stay_until = date.today() + timedelta(days=10)
    mos_data.save()

    call_command("update_reminders", "--only", "legal-stay")
    reminder = Reminder.objects.get(client=client, reminder_type="legal_stay")
    assert reminder.get_reminder_type_display() != "legal_stay"

    call_command("update_reminders", "--only", "legal-stay")
    assert Reminder.objects.filter(client=client, reminder_type="legal_stay", is_active=True).count() == 1


def test_legal_stay_ignored_for_submitted_and_later_stages(db):
    client = Client.objects.create(
        first_name="L",
        last_name="S",
        application_purpose="work",
        workflow_stage="application_submitted",
    )
    mos_data = client.mos_application_data
    mos_data.legal_stay_until = date.today() + timedelta(days=10)
    mos_data.save()

    call_command("update_reminders", "--only", "legal-stay")
    assert not Reminder.objects.filter(client=client, reminder_type="legal_stay").exists()


def test_get_health_alerts_legal_stay_logic(db):
    from django.utils.translation import gettext_lazy as _
    # 1. new_client stage with legal stay ending soon (20 days) via onboarding fallback
    client_new = Client.objects.create(
        first_name="New",
        last_name="Client",
        application_purpose="work",
        workflow_stage="new_client",
    )
    mos_data = client_new.mos_application_data
    mos_data.legal_stay_until = date.today() + timedelta(days=20)
    mos_data.save()

    alerts_new = client_new.get_health_alerts()
    expected_title = str(_("Основание пребывания скоро истекает"))
    assert any(a["level"] == "warning" and str(a["title"]) == expected_title for a in alerts_new)

    # 2. application_submitted stage with the same expiring legal stay
    client_submitted = Client.objects.create(
        first_name="Submitted",
        last_name="Client",
        application_purpose="work",
        workflow_stage="application_submitted",
    )
    mos_data_sub = client_submitted.mos_application_data
    mos_data_sub.legal_stay_until = date.today() + timedelta(days=20)
    mos_data_sub.save()

    alerts_submitted = client_submitted.get_health_alerts()
    expected_title_expired = str(_("Основание пребывания уже истекло"))
    assert not any(str(a["title"]) in [expected_title, expected_title_expired] for a in alerts_submitted)



