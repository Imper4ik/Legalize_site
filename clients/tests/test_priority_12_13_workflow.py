from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from django.core import mail
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from clients.constants import DocumentType
from clients.models import Client, Document, DocumentRequirement, EmailLog, Payment, Reminder
from clients.services.family import calculate_family_income, create_family_member, get_or_create_family_group
from clients.services.notifications import (
    _get_expired_documents_context,
    _get_expiring_documents_context,
    send_appointment_notification_email,
    send_expired_documents_email,
)
from clients.services.zus import expected_zus_months, missing_zus_months
from clients.tests.factories import create_admin_user, create_staff_user
from clients.use_cases.client_records import finalize_client_update, snapshot_client_update_state


def make_client(**overrides) -> Client:
    defaults = {
        "first_name": "Ira",
        "last_name": "Kowalska",
        "email": "ira@example.com",
        "phone": "+48123123123",
        "citizenship": "UA",
        "application_purpose": "work",
        "language": "pl",
    }
    defaults.update(overrides)
    return Client.objects.create(**defaults)


def require_passport(purpose: str = "work") -> DocumentRequirement:
    DocumentRequirement.objects.filter(application_purpose=purpose).delete()
    return DocumentRequirement.objects.create(
        application_purpose=purpose,
        document_type=DocumentType.PASSPORT.value,
        is_required=True,
        position=0,
    )


@pytest.mark.django_db
def test_document_preview_is_inline_and_download_is_attachment(logged_in_staff, sample_client):
    document = Document.objects.create(client=sample_client, document_type=DocumentType.PASSPORT.value)
    document.file.save("passport.pdf", ContentFile(b"%PDF-1.4"), save=True)

    preview = logged_in_staff.get(reverse("clients:document_preview", kwargs={"doc_id": document.pk}))
    download = logged_in_staff.get(reverse("clients:document_download", kwargs={"doc_id": document.pk}))

    assert preview.status_code == 200
    assert preview["Content-Disposition"].startswith("inline")
    assert download.status_code == 200
    assert download["Content-Disposition"].startswith("attachment")


@pytest.mark.django_db
def test_missing_documents_weekly_email_sends_once_for_waiting_decision_client():
    require_passport()
    client = make_client(workflow_stage="waiting_decision", fingerprints_date=date(2026, 4, 1))
    today = date(2026, 5, 18)
    mail.outbox = []

    with patch("clients.services.notifications.timezone.localdate", return_value=today):
        with patch("clients.services.notifications._send_confirmation_email"):
            call_command("update_reminders")
            call_command("update_reminders")

    assert len(mail.outbox) == 1
    assert EmailLog.objects.filter(client=client, template_type="missing_documents").count() == 1


@pytest.mark.django_db
def test_missing_documents_weekly_email_skips_without_missing_docs_or_email():
    require_passport()
    with_doc = make_client(
        email="with-doc@example.com",
        workflow_stage="waiting_decision",
        fingerprints_date=date(2026, 4, 1),
    )
    Document.objects.create(
        client=with_doc,
        document_type=DocumentType.PASSPORT.value,
        file=SimpleUploadedFile("passport.pdf", b"x", content_type="application/pdf"),
    )
    make_client(
        email="",
        workflow_stage="waiting_decision",
        fingerprints_date=date(2026, 4, 1),
    )
    mail.outbox = []

    with patch("clients.services.notifications._send_confirmation_email"):
        call_command("update_reminders")

    assert mail.outbox == []
    assert EmailLog.objects.filter(template_type="missing_documents").count() == 0


@pytest.mark.django_db
def test_expired_documents_email_skips_empty_and_expiry_boundaries(sample_client):
    today = timezone.localdate()

    assert _get_expired_documents_context(sample_client) is None
    assert send_expired_documents_email(sample_client) == 0

    expired = Document.objects.create(
        client=sample_client,
        document_type=DocumentType.PASSPORT.value,
        file=SimpleUploadedFile("expired.pdf", b"x", content_type="application/pdf"),
        expiry_date=today - timedelta(days=1),
    )
    today_doc = Document.objects.create(
        client=sample_client,
        document_type=DocumentType.PHOTOS.value,
        file=SimpleUploadedFile("today.pdf", b"x", content_type="application/pdf"),
        expiry_date=today,
    )
    soon_doc = Document.objects.create(
        client=sample_client,
        document_type=DocumentType.HEALTH_INSURANCE.value,
        file=SimpleUploadedFile("soon.pdf", b"x", content_type="application/pdf"),
        expiry_date=today + timedelta(days=7),
    )

    expired_context = _get_expired_documents_context(sample_client)
    expiring_context = _get_expiring_documents_context(sample_client, [expired, today_doc, soon_doc])

    assert list(expired_context["expired_documents"]) == [expired]
    assert expired in expiring_context["expired_documents"]
    assert today_doc in expiring_context["expiring_soon_documents"]
    assert soon_doc in expiring_context["expiring_later_documents"]


@pytest.mark.django_db
def test_payment_reminders_use_due_date_lte_today_and_do_not_duplicate(sample_client):
    today = timezone.localdate()
    future_payment = Payment.objects.create(
        client=sample_client,
        service_description="consultation",
        total_amount=Decimal("100.00"),
        status="pending",
        due_date=today + timedelta(days=1),
    )
    assert not Reminder.objects.filter(payment=future_payment).exists()

    due_today = Payment.objects.create(
        client=sample_client,
        service_description="consultation",
        total_amount=Decimal("100.00"),
        status="pending",
        due_date=today,
    )
    overdue_partial = Payment.objects.create(
        client=sample_client,
        service_description="consultation",
        total_amount=Decimal("100.00"),
        amount_paid=Decimal("25.00"),
        status="partial",
        due_date=today - timedelta(days=1),
    )

    call_command("update_reminders")
    call_command("update_reminders")

    assert Reminder.objects.filter(payment=due_today, is_active=True).count() == 1
    assert Reminder.objects.filter(payment=overdue_partial, is_active=True).count() == 1
    assert not Reminder.objects.filter(payment=future_payment).exists()


@pytest.mark.django_db
def test_health_alerts_missing_docs_and_payment_due_dates():
    sample_client = make_client(application_purpose="custom_health")
    require_passport("custom_health")
    future_payment = Payment.objects.create(
        client=sample_client,
        service_description="consultation",
        total_amount=Decimal("100.00"),
        status="pending",
        due_date=timezone.localdate() + timedelta(days=2),
    )
    assert not Reminder.objects.filter(payment=future_payment).exists()

    alerts = sample_client.get_health_alerts()
    missing_alert = next(alert for alert in alerts if str(alert["title"]) == "Не все документы собраны")
    assert missing_alert["count"] == 1
    assert all(str(alert["title"]) != "Просроченные оплаты" for alert in alerts)

    Payment.objects.create(
        client=sample_client,
        service_description="consultation",
        total_amount=Decimal("100.00"),
        status="pending",
        due_date=timezone.localdate() - timedelta(days=1),
    )
    alerts = sample_client.get_health_alerts()
    assert any(str(alert["title"]) == "Просроченные оплаты" for alert in alerts)


@pytest.mark.django_db
def test_fingerprints_date_change_does_not_send_expired_email_and_appointment_is_idempotent(sample_client):
    previous_values = snapshot_client_update_state(sample_client)
    previous_fingerprints_date = sample_client.fingerprints_date
    sample_client.fingerprints_date = timezone.localdate()
    sample_client.save(update_fields=["fingerprints_date"])
    send_expired = Mock(return_value=1)

    result = finalize_client_update(
        client=sample_client,
        actor=None,
        previous_values=previous_values,
        previous_fingerprints_date=previous_fingerprints_date,
        new_fingerprints_date=sample_client.fingerprints_date,
        send_expired_email=send_expired,
    )

    assert not result.expired_documents_email_sent
    send_expired.assert_not_called()

    mail.outbox = []
    with patch("clients.services.notifications._send_confirmation_email"):
        assert send_appointment_notification_email(sample_client) == 1
        assert send_appointment_notification_email(sample_client) == 0
    assert len(mail.outbox) == 1


def test_expected_zus_months_respects_15th_day_cutoff():
    fingerprints = date(2026, 1, 20)

    assert expected_zus_months(fingerprints, today=date(2026, 4, 10)) == [date(2026, 2, 1)]
    assert expected_zus_months(fingerprints, today=date(2026, 4, 16)) == [
        date(2026, 2, 1),
        date(2026, 3, 1),
    ]


@pytest.mark.django_db
def test_zus_rca_uploaded_period_closes_month_and_duplicates_are_blocked(sample_client):
    sample_client.fingerprints_date = date(2026, 1, 20)
    sample_client.save(update_fields=["fingerprints_date"])
    Document.objects.create(
        client=sample_client,
        document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
        file=SimpleUploadedFile("zus-feb.pdf", b"x", content_type="application/pdf"),
        zus_period_month=date(2026, 2, 20),
    )

    assert missing_zus_months(sample_client, today=date(2026, 4, 16)) == [date(2026, 3, 1)]

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Document.objects.create(
                client=sample_client,
                document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
                file=SimpleUploadedFile("zus-feb-duplicate.pdf", b"x", content_type="application/pdf"),
                zus_period_month=date(2026, 2, 1),
            )


@pytest.mark.django_db
def test_family_roles_checklists_child_client_link_and_dashboard_access(client):
    admin = create_admin_user()
    sponsor = make_client(
        first_name="Sponsor",
        last_name="Client",
        email="sponsor@example.com",
        family_role="sponsor",
        assigned_staff=admin,
    )
    spouse = create_family_member(
        sponsor=sponsor,
        role="family_spouse",
        first_name="Spouse",
        last_name="Client",
        email="spouse@example.com",
        assigned_staff=admin,
    )
    child_member = create_family_member(
        sponsor=sponsor,
        role="family_child",
        first_name="Child",
        last_name="Client",
        email="child@example.com",
        assigned_staff=admin,
    )

    spouse_codes = {item["code"] for item in spouse.get_document_checklist()}
    child_codes = {item["code"] for item in child_member.get_document_checklist()}
    assert "marriage_certificate" in spouse_codes
    assert "birth_certificate" in child_codes
    assert child_member.pk != sponsor.pk
    assert child_member.sponsor_client == sponsor

    client.force_login(admin)
    assert client.get(reverse("clients:family_dashboard", kwargs={"pk": sponsor.pk})).status_code == 200

    other_staff = create_staff_user()
    client.force_login(other_staff)
    assert client.get(reverse("clients:family_dashboard", kwargs={"pk": sponsor.pk})).status_code == 404


@pytest.mark.django_db
def test_family_income_required_amount_rent_free_housing_and_risks():
    sponsor = make_client(first_name="Sponsor", last_name="Income", email="income@example.com", family_role="sponsor")
    create_family_member(
        sponsor=sponsor,
        role="family_spouse",
        first_name="Spouse",
        last_name="Income",
        email="spouse-income@example.com",
    )
    create_family_member(
        sponsor=sponsor,
        role="family_child",
        first_name="Child",
        last_name="Income",
        email="child-income@example.com",
    )
    group = get_or_create_family_group(sponsor)
    group.sponsor_monthly_income = Decimal("5000.00")
    group.monthly_support_per_person = Decimal("823.00")
    group.monthly_housing_cost = Decimal("700.00")
    group.save()

    income = calculate_family_income(group)
    assert income.required_income == Decimal("3169.00")
    assert income.housing_cost == Decimal("700.00")
    assert income.is_sufficient
    assert income.risks == ()

    group.meldunek_free_housing = True
    group.save()
    income = calculate_family_income(group)
    assert income.housing_cost == Decimal("0.00")
    assert income.required_income == Decimal("2469.00")

    group.sponsor_monthly_income = Decimal("2000.00")
    group.save()
    assert calculate_family_income(group).risks

    group.sponsor_monthly_income = None
    group.save()
    assert calculate_family_income(group).risks
