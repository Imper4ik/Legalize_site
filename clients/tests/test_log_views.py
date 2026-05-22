from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.paginator import Paginator
from django.template.loader import get_template
from django.test import RequestFactory
from django.urls import reverse
from django.utils import translation

from clients.models import ClientActivity, Document, EmailLog, Payment


def assert_log_page_uses_dark_safe_chrome(content: str) -> None:
    assert "client-list-filters" in content
    assert "table-container" in content
    assert "table-modern" in content
    assert "card-body bg-light rounded" not in content
    assert "table-light" not in content


@pytest.mark.django_db
def test_email_logs_page_renders(logged_in_admin, sample_client):
    EmailLog.objects.create(
        client=sample_client,
        subject="Rendered email log",
        body="Body",
        recipients="client@example.com",
        delivery_status=EmailLog.DELIVERY_STATUS_SENT,
        sent_by=logged_in_admin._admin_user,
    )
    EmailLog.objects.create(
        client=sample_client,
        subject="System email log",
        body="Body",
        recipients="client@example.com",
        delivery_status=EmailLog.DELIVERY_STATUS_SENT,
        sent_by=None,
    )

    response = logged_in_admin.get(reverse("clients:email_logs"))

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert_log_page_uses_dark_safe_chrome(content)
    assert "Rendered email log" in content
    assert "System email log" in content


@pytest.mark.django_db
def test_staff_activity_logs_page_renders(logged_in_admin, sample_client):
    document = Document.objects.create(
        client=sample_client,
        document_type="custom_document",
        file="documents/activity.pdf",
    )
    payment = Payment.objects.create(
        client=sample_client,
        service_description="consultation",
        total_amount=Decimal("125.00"),
    )
    ClientActivity.objects.create(
        client=sample_client,
        actor=logged_in_admin._admin_user,
        event_type="client_updated",
        summary="Rendered activity log",
        document=document,
        payment=payment,
    )

    response = logged_in_admin.get(reverse("clients:staff_activity_logs"))

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert_log_page_uses_dark_safe_chrome(content)
    assert "Rendered activity log" in content
    assert "Custom document" in content
    assert "125" in content
    assert "PLN" in content


@pytest.mark.django_db
def test_staff_activity_logs_use_russian_labels_in_russian_locale(logged_in_admin, sample_client):
    ClientActivity.objects.create(
        client=sample_client,
        actor=logged_in_admin._admin_user,
        event_type="client_viewed",
        summary="Locale activity marker",
    )

    with translation.override("ru"):
        response = logged_in_admin.get(
            reverse("clients:staff_activity_logs"),
            HTTP_ACCEPT_LANGUAGE="ru",
        )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Логи сотрудников" in content
    assert "Карточка клиента открыта" in content
    assert "Logi pracowników" not in content
    assert "Karta klienta jest otwarta" not in content
    assert "bg-light text-dark" not in content


@pytest.mark.django_db
def test_client_get_full_name(sample_client):
    assert sample_client.get_full_name() == "Test Client"


@pytest.mark.django_db
@pytest.mark.parametrize("url_name", ["clients:email_logs", "clients:staff_activity_logs"])
def test_log_pages_reject_plain_staff(logged_in_staff, url_name):
    response = logged_in_staff.get(reverse(url_name))

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("url_name", ["clients:email_logs", "clients:staff_activity_logs"])
def test_log_pages_allow_manager(client, manager_user, sample_client, url_name):
    if url_name == "clients:email_logs":
        EmailLog.objects.create(
            client=sample_client,
            subject="Manager email log",
            body="Body",
            recipients="client@example.com",
            delivery_status=EmailLog.DELIVERY_STATUS_SENT,
            sent_by=manager_user,
        )
    else:
        ClientActivity.objects.create(
            client=sample_client,
            actor=manager_user,
            event_type="client_updated",
            summary="Manager activity log",
        )
    client.force_login(manager_user)

    response = client.get(reverse(url_name))

    assert response.status_code == 200
    assert "Manager" in response.content.decode("utf-8")


def test_pagination_partial_preserves_filters_without_duplicate_page():
    request = RequestFactory().get("/staff/logs/emails/?status=sent&page=2")
    page = Paginator(list(range(60)), 50).page(2)

    rendered = get_template("clients/partials/pagination.html").render(
        {"is_paginated": True, "page_obj": page},
        request,
    )

    assert "status=sent" in rendered
    assert "page=1" in rendered
    assert "page=1&amp;status" not in rendered
    assert rendered.count("page=") == 1
