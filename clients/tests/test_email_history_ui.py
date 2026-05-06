import pytest
from django.urls import reverse
from django.utils import timezone
from clients.models import Client, EmailLog
from datetime import timedelta

@pytest.mark.django_db
def test_email_history_visibility(admin_client):
    client = Client.objects.create(
        first_name="Test",
        last_name="User",
        email="test@example.com",
    )

    # Create 5 email logs with different timestamps
    now = timezone.now()
    for i in range(5):
        EmailLog.objects.create(
            client=client,
            subject=f"Subject {i}",
            body=f"Body {i}",
            recipients="test@example.com",
            sent_at=now - timedelta(minutes=i)
        )

    url = reverse("clients:client_detail", kwargs={"pk": client.pk})
    response = admin_client.get(url)

    assert response.status_code == 200
    content = response.content.decode("utf-8")

    # Check that all 5 subjects are present
    for i in range(5):
        assert f"Subject {i}" in content

    # Check classes for visible/hidden logs
    # 3 newest should NOT have d-none
    # 0, 1, 2 are newest because we created them with sent_at = now, now-1, now-2
    assert 'class="email-log-row "' in content # Subject 0 (most recent)

    # Check that the toggle button exists and shows count 2
    assert 'email-history-toggle' in content
    assert 'data-hidden-count="2"' in content

@pytest.mark.django_db
def test_email_history_no_toggle_for_3_logs(admin_client):
    client = Client.objects.create(
        first_name="Test",
        last_name="User",
        email="test@example.com",
    )

    for i in range(3):
        EmailLog.objects.create(
            client=client,
            subject=f"Subject {i}",
            body=f"Body {i}",
            recipients="test@example.com"
        )

    url = reverse("clients:client_detail", kwargs={"pk": client.pk})
    response = admin_client.get(url)

    assert response.status_code == 200
    content = response.content.decode("utf-8")

    assert 'email-history-toggle' not in content
