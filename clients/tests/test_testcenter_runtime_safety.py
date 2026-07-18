from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from clients.demo.demo_runner import ensure_demo_center_enabled
from clients.models import Case, Client
from clients.testing.e2e_runner import ensure_test_center_enabled


@override_settings(ENABLE_TEST_CENTER=False)
def test_test_center_flag_disables_even_superuser() -> None:
    with pytest.raises(PermissionDenied):
        ensure_test_center_enabled(user=SimpleNamespace(is_superuser=True))


@override_settings(DEMO_MODE_ENABLED=False)
def test_demo_center_flag_disables_even_superuser() -> None:
    with pytest.raises(PermissionDenied):
        ensure_demo_center_enabled(user=SimpleNamespace(is_superuser=True))


@pytest.mark.django_db
def test_test_data_only_reminders_do_not_process_production_clients() -> None:
    today = timezone.localdate()
    production_client = Client.objects.create(
        first_name="Production",
        last_name="Client",
        email="production@example.test",
        application_purpose="work",
    )
    test_client = Client.objects.create(
        first_name="Test",
        last_name="Client",
        email="test-center@example.test",
        application_purpose="work",
        is_test_data=True,
    )
    for client in (production_client, test_client):
        case = Case.objects.get(client=client)
        case.workflow_stage = "waiting_decision"
        case.fingerprints_date = today - timedelta(days=1)
        case.save(update_fields=["workflow_stage", "fingerprints_date"])

    with patch(
        "clients.management.commands.update_reminders.send_missing_documents_email",
        return_value=0,
    ) as send:
        call_command("update_reminders", "--only", "missing-docs", "--test-data-only")

    assert [call.args[0].pk for call in send.call_args_list] == [test_client.pk]
