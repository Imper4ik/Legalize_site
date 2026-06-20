from __future__ import annotations

from datetime import date, timedelta

from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from clients.constants import DocumentType
from clients.models import Client, Document, EmailLog, MOSApplicationData, Payment, Reminder, StaffTask


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


@override_settings(LANGUAGE_CODE="ru")
def test_get_health_alerts_new_card_application_mentions_case_joining(db):
    client = Client.objects.create(
        first_name="NewCard",
        last_name="CaseJoin",
        application_purpose="work",
        fingerprints_date=date.today() - timedelta(days=7),
    )
    mos_data = client.mos_application_data
    mos_data.new_residence_card_application_status = MOSApplicationData.NEW_CARD_STATUS_YES
    mos_data.save(update_fields=["new_residence_card_application_status"])

    alerts = client.get_health_alerts()

    matching = [alert for alert in alerts if str(alert["title"]) == "Новая подача требует проверки дела"]
    assert len(matching) == 1
    assert matching[0]["level"] == "warning"
    assert "присоединение к делу" in str(matching[0]["message"])

    mos_data.new_residence_card_case_number = "WSC-II-77/2026"
    mos_data.save(update_fields=["new_residence_card_case_number"])
    alerts_with_mos_number = client.get_health_alerts()
    matching_with_mos_number = [
        alert for alert in alerts_with_mos_number if str(alert["title"]) == "Новая подача требует проверки дела"
    ]
    assert len(matching_with_mos_number) == 1
    assert "Перенесите номер или проверьте присоединение к делу" in str(matching_with_mos_number[0]["message"])

    client.case_number = "WSC-II-77/2026"
    client.save(update_fields=["case_number"])
    alerts_with_client_case = client.get_health_alerts()
    assert not any(str(alert["title"]) == "Новая подача требует проверки дела" for alert in alerts_with_client_case)

def test_send_legal_stay_email_critical_interval(db):
    from unittest.mock import patch

    from django.contrib.auth import get_user_model

    from clients.services.notifications import send_legal_stay_email

    User = get_user_model()
    staff = User.objects.create_user(username="staff_user", email="staff@example.com", is_staff=True)

    client = Client.objects.create(
        first_name="John",
        last_name="Doe",
        email="client@example.com",
        assigned_staff=staff,
    )

    # Case 1: Legal stay expiring in 20 days (>14 days) -> sent only to client, once
    with patch("clients.services.notifications._send_email", return_value=1) as mock_send:
        with patch("django.utils.timezone.localdate", return_value=date(2026, 5, 30)):
            res = send_legal_stay_email(client, date(2026, 6, 19), date(2026, 6, 19))
            assert res == 1
            mock_send.assert_called_once()
            args, kwargs = mock_send.call_args
            assert args[2] == ["client@example.com"]
            assert len(kwargs["idempotency_key"]) == 64

    # Case 2: Legal stay expiring in 10 days (<=14 days) on date(2026, 5, 30)
    with patch("clients.services.notifications._send_email", return_value=1) as mock_send:
        with patch("django.utils.timezone.localdate", return_value=date(2026, 5, 30)):
            res = send_legal_stay_email(client, date(2026, 6, 9), date(2026, 6, 9))
            assert res == 1
            mock_send.assert_called_once()
            args, kwargs = mock_send.call_args
            assert args[2] == ["client@example.com", "staff@example.com"]
            key_first = kwargs["idempotency_key"]

    # Case 3: Same day, should generate same key
    with patch("clients.services.notifications._send_email", return_value=1) as mock_send:
        with patch("django.utils.timezone.localdate", return_value=date(2026, 5, 30)):
            send_legal_stay_email(client, date(2026, 6, 9), date(2026, 6, 9))
            args, kwargs = mock_send.call_args
            assert kwargs["idempotency_key"] == key_first

    # Case 4: Day before (same interval)
    with patch("clients.services.notifications._send_email", return_value=1) as mock_send:
        with patch("django.utils.timezone.localdate", return_value=date(2026, 5, 29)):
            send_legal_stay_email(client, date(2026, 6, 9), date(2026, 6, 9))
            args, kwargs = mock_send.call_args
            key_day_before = kwargs["idempotency_key"]
            assert key_day_before == key_first

    # Case 5: Day after (different interval)
    with patch("clients.services.notifications._send_email", return_value=1) as mock_send:
        with patch("django.utils.timezone.localdate", return_value=date(2026, 5, 31)):
            send_legal_stay_email(client, date(2026, 6, 9), date(2026, 6, 9))
            args, kwargs = mock_send.call_args
            key_day_after = kwargs["idempotency_key"]
            assert key_day_after != key_first


@override_settings(LANGUAGE_CODE="ru")
def test_get_automatic_checks_compilation(db):
    client = Client.objects.create(
        first_name="Check",
        last_name="Tester",
        application_purpose="work",
        workflow_stage="new_client",
    )
    checks = client.get_automatic_checks()
    # Expecting exactly 10 checks to be compiled
    assert len(checks) == 10

    # Legal stay check
    stay_check = next(c for c in checks if c["label"] == "Легальность пребывания")
    assert stay_check["status"] == "warning"
    assert "не указана" in stay_check["message"].lower()

    # Checklist completion check
    checklist_check = next(c for c in checks if c["label"] == "Комплект документов")
    assert checklist_check["status"] == "warning"

    # Staff tasks check
    tasks_check = next(c for c in checks if c["label"] == "Задачи по делу")
    assert tasks_check["status"] == "success"


def test_document_save_and_delete_clears_onboarding_cache(db):
    from unittest.mock import patch
    client = Client.objects.create(
        first_name="Cache",
        last_name="Clearer",
        application_purpose="work",
    )

    with patch("clients.services.onboarding_purposes.clear_onboarding_notifications_cache") as mock_clear:
        doc = Document.objects.create(
            client=client,
            document_type=DocumentType.PASSPORT.value,
            file="documents/test_cache.pdf",
        )
        mock_clear.assert_called_with(client)

        mock_clear.reset_mock()
        doc.delete()
        mock_clear.assert_called_with(client)


@override_settings(LANGUAGE_CODE="ru")
def test_health_alert_ocr_and_wezwanie_actions(db):
    client = Client.objects.create(
        first_name="OCR",
        last_name="Tester",
        application_purpose="work",
        case_number="",
    )

    doc_passport = Document.objects.create(
        client=client,
        document_type=DocumentType.PASSPORT.value,
        file="documents/passport_ocr.pdf",
        awaiting_confirmation=True,
    )

    doc_wezwanie = Document.objects.create(
        client=client,
        document_type=DocumentType.WEZWANIE.value,
        file="documents/wezwanie_ocr.pdf",
        awaiting_confirmation=True,
    )

    alerts = client.get_health_alerts()

    ocr_alert = next(a for a in alerts if a["title"] == "Есть OCR-данные без подтверждения")
    assert "actions" in ocr_alert
    assert len(ocr_alert["actions"]) == 2
    assert any(act["doc_id"] == doc_passport.id and act["is_ocr_review"] for act in ocr_alert["actions"])
    assert any(act["doc_id"] == doc_wezwanie.id and act["is_ocr_review"] for act in ocr_alert["actions"])

    wezwanie_alert = next(a for a in alerts if a["title"] == "Есть wezwanie без номера дела")
    assert "actions" in wezwanie_alert
    assert len(wezwanie_alert["actions"]) == 1
    assert wezwanie_alert["actions"][0]["doc_id"] == doc_wezwanie.id
    assert wezwanie_alert["actions"][0]["is_ocr_review"] is True

    doc_wezwanie.awaiting_confirmation = False
    doc_wezwanie.save()

    alerts = client.get_health_alerts()
    wezwanie_alert = next(a for a in alerts if a["title"] == "Есть wezwanie без номера дела")
    assert "actions" in wezwanie_alert
    assert wezwanie_alert["actions"][0]["url"] == reverse("clients:document_preview", kwargs={"doc_id": doc_wezwanie.id})
    assert wezwanie_alert["actions"][0].get("is_ocr_review") is not True






