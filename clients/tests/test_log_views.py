from __future__ import annotations

import pytest
from django.core.paginator import Paginator
from django.template.loader import get_template
from django.test import RequestFactory
from django.urls import reverse

from clients.models import ClientActivity, EmailLog


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
    assert "Rendered email log" in content
    assert "System email log" in content


@pytest.mark.django_db
def test_staff_activity_logs_page_renders(logged_in_admin, sample_client):
    ClientActivity.objects.create(
        client=sample_client,
        actor=logged_in_admin._admin_user,
        event_type="client_updated",
        summary="Rendered activity log",
    )

    response = logged_in_admin.get(reverse("clients:staff_activity_logs"))

    assert response.status_code == 200
    assert "Rendered activity log" in response.content.decode("utf-8")


@pytest.mark.django_db
@pytest.mark.parametrize("url_name", ["clients:email_logs", "clients:staff_activity_logs"])
def test_log_pages_reject_plain_staff(logged_in_staff, url_name):
    response = logged_in_staff.get(reverse(url_name))

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("url_name", ["clients:email_logs", "clients:staff_activity_logs"])
def test_log_pages_allow_manager(client, manager_user, url_name):
    client.force_login(manager_user)

    response = client.get(reverse(url_name))

    assert response.status_code == 200


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
