"""Tests for P1 improvements: family badges, UI permissions, metrics SLA,
admin dashboard performance, ZIP export limits, update_reminders separation,
and database indexes.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest
from django.test import Client as DjangoClient, override_settings
from django.urls import reverse
from django.utils import timezone

from clients.models import Client, Document, Payment, Reminder
from clients.tests.factories import (
    create_admin_user,
    create_manager_user,
    create_readonly_user,
    create_staff_user,
)


# ───────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────

def _make_client(db, **kwargs):
    defaults = dict(
        first_name="Test",
        last_name="Client",
        email="test@example.com",
        phone="+48000000000",
        citizenship="Poland",
        application_purpose="work",
    )
    defaults.update(kwargs)
    return Client.objects.create(**defaults)


# ───────────────────────────────────────────────────────────────────
# 1. update_reminders: email not called twice from document section
# ───────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestUpdateRemindersEmailSeparation:
    """Verify create_document_reminders creates reminders only (no email)."""

    def test_create_document_reminders_does_not_send_email(self, sample_client):
        """create_document_reminders should NOT call send_expiring_documents_email."""
        today = timezone.localdate()
        Document.objects.create(
            client=sample_client,
            document_type="passport",
            file="test.pdf",
            expiry_date=today + timedelta(days=5),  # within 7 days = expiring soon
        )

        from clients.management.commands.update_reminders import Command

        cmd = Command()
        cmd.stdout = StringIO()

        with patch(
            "clients.management.commands.update_reminders.send_expiring_documents_email"
        ) as mock_email:
            cmd.create_document_reminders()
            mock_email.assert_not_called()

        # Reminder should be created
        assert Reminder.objects.filter(client=sample_client, reminder_type="document").count() == 1

    def test_dry_run_creates_nothing(self, sample_client):
        """--dry-run should not create reminders or send emails."""
        today = timezone.localdate()
        Document.objects.create(
            client=sample_client,
            document_type="passport",
            file="test.pdf",
            expiry_date=today + timedelta(days=5),
        )

        from clients.management.commands.update_reminders import Command

        cmd = Command()
        cmd.stdout = StringIO()

        with patch(
            "clients.management.commands.update_reminders.send_expiring_documents_email"
        ) as mock_email:
            cmd.create_document_reminders(dry_run=True)
            mock_email.assert_not_called()

        assert Reminder.objects.filter(client=sample_client).count() == 0


# ───────────────────────────────────────────────────────────────────
# 3. Family badges in client list
# ───────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestFamilyBadgesInList:

    def test_sponsor_badge_rendered(self):
        admin = create_admin_user()
        sponsor = _make_client(None, first_name="Sponsor", last_name="Main", email="s@e.com")
        _make_client(
            None,
            first_name="Spouse",
            last_name="Dep",
            email="sp@e.com",
            application_purpose="family",
            family_role="family_spouse",
            sponsor_client=sponsor,
        )

        client = DjangoClient()
        client.force_login(admin)
        response = client.get(reverse("clients:client_list"))
        content = response.content.decode()
        assert "Спонсор:" in content or "bi-people-fill" in content

    def test_spouse_badge_rendered(self):
        admin = create_admin_user()
        sponsor = _make_client(None, first_name="Sponsor", last_name="Parent", email="sp2@e.com")
        _make_client(
            None,
            first_name="Wife",
            last_name="Dep",
            email="w@e.com",
            application_purpose="family",
            family_role="family_spouse",
            sponsor_client=sponsor,
        )

        client = DjangoClient()
        client.force_login(admin)
        response = client.get(reverse("clients:client_list"))
        content = response.content.decode()
        assert "Супруг/супруга" in content or "bi-heart-fill" in content

    def test_child_badge_rendered(self):
        admin = create_admin_user()
        sponsor = _make_client(None, first_name="Parent", last_name="Main", email="p@e.com")
        _make_client(
            None,
            first_name="Child",
            last_name="Kid",
            email="c@e.com",
            application_purpose="family",
            family_role="family_child",
            sponsor_client=sponsor,
        )

        client = DjangoClient()
        client.force_login(admin)
        response = client.get(reverse("clients:client_list"))
        content = response.content.decode()
        assert "Ребёнок" in content or "bi-emoji-smile" in content


# ───────────────────────────────────────────────────────────────────
# 4. UI permissions: hide buttons
# ───────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestUIPermissions:

    def test_readonly_no_delete_button(self):
        readonly = create_readonly_user()
        _make_client(None, first_name="Test", last_name="Del", email="d@e.com")

        c = DjangoClient()
        c.force_login(readonly)
        response = c.get(reverse("clients:client_list"))
        content = response.content.decode()
        assert "btn-delete-" not in content
        assert "client_delete" not in content or "bi-trash" not in content

    def test_readonly_no_mass_email_button(self):
        readonly = create_readonly_user()
        c = DjangoClient()
        c.force_login(readonly)
        response = c.get(reverse("clients:client_list"))
        content = response.content.decode()
        assert "btn-mass-email" not in content

    def test_admin_sees_delete_button(self):
        admin = create_admin_user()
        sample = _make_client(None, first_name="A", last_name="B", email="ab@e.com")

        c = DjangoClient()
        c.force_login(admin)
        response = c.get(reverse("clients:client_list"))
        content = response.content.decode()
        assert "bi-trash" in content

    def test_admin_sees_mass_email_button(self):
        admin = create_admin_user()
        c = DjangoClient()
        c.force_login(admin)
        response = c.get(reverse("clients:client_list"))
        content = response.content.decode()
        assert "btn-mass-email" in content

    def test_backend_delete_still_protected(self):
        """ReadOnly user cannot access delete URL directly."""
        readonly = create_readonly_user()
        sample = _make_client(None, first_name="X", last_name="Y", email="xy@e.com")

        c = DjangoClient()
        c.force_login(readonly)
        response = c.get(reverse("clients:client_delete", kwargs={"pk": sample.pk}))
        assert response.status_code == 403


# ───────────────────────────────────────────────────────────────────
# 5. Metrics SLA
# ───────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestMetricsSLA:

    def test_overdue_sla_counts_waiting_decision_old_fingerprints(self):
        admin = create_admin_user()
        today = timezone.localdate()
        _make_client(
            None,
            first_name="Old",
            last_name="Case",
            email="old@e.com",
            workflow_stage="waiting_decision",
            fingerprints_date=today - timedelta(days=200),
            decision_date=None,
        )

        c = DjangoClient()
        c.force_login(admin)
        response = c.get(reverse("clients:metrics_dashboard"))
        assert response.status_code == 200
        assert response.context["overdue_sla"] == 1

    def test_closed_old_case_not_counted_as_overdue(self):
        admin = create_admin_user()
        today = timezone.localdate()
        _make_client(
            None,
            first_name="Closed",
            last_name="Case",
            email="cl@e.com",
            workflow_stage="closed",
            fingerprints_date=today - timedelta(days=200),
            decision_date=today - timedelta(days=10),
        )

        c = DjangoClient()
        c.force_login(admin)
        response = c.get(reverse("clients:metrics_dashboard"))
        assert response.context["overdue_sla"] == 0

    def test_recent_fingerprints_not_overdue(self):
        admin = create_admin_user()
        today = timezone.localdate()
        _make_client(
            None,
            first_name="Recent",
            last_name="Case",
            email="rc@e.com",
            workflow_stage="waiting_decision",
            fingerprints_date=today - timedelta(days=30),
            decision_date=None,
        )

        c = DjangoClient()
        c.force_login(admin)
        response = c.get(reverse("clients:metrics_dashboard"))
        assert response.context["overdue_sla"] == 0

    def test_start_end_get_filters(self):
        admin = create_admin_user()
        today = timezone.localdate()

        c = DjangoClient()
        c.force_login(admin)
        response = c.get(
            reverse("clients:metrics_dashboard"),
            {"start": (today - timedelta(days=7)).isoformat(), "end": today.isoformat()},
        )
        assert response.status_code == 200
        assert response.context["start_date"] == today - timedelta(days=7)
        assert response.context["end_date"] == today


# ───────────────────────────────────────────────────────────────────
# 7. ZIP export size limit
# ───────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestZipExportSizeLimit:

    def test_small_export_works(self):
        from clients.services.export import generate_client_zip

        client_obj = _make_client(None, first_name="Small", last_name="Export", email="se@e.com")
        buf = generate_client_zip(client_obj)
        assert buf.getbuffer().nbytes > 0

    def test_export_over_limit_raises(self):
        from clients.services.export import ExportSizeLimitExceeded, _check_export_size_limit

        client_obj = _make_client(None, first_name="Big", last_name="Export", email="be@e.com")

        # Limit to 0 MB — any file would exceed
        with pytest.raises(ExportSizeLimitExceeded):
            with override_settings(MAX_TOTAL_CLIENT_EXPORT_MB=0):
                # Create a document with a file
                doc = Document.objects.create(
                    client=client_obj,
                    document_type="passport",
                    file="test.pdf",
                )
                # Mock the file size to be large
                with patch.object(type(doc.file), "size", new_callable=lambda: property(lambda self: 1024 * 1024)):
                    with patch(
                        "clients.services.export.document_file_exists", return_value=True
                    ):
                        _check_export_size_limit(client_obj, 0)


# ───────────────────────────────────────────────────────────────────
# 8. Migration check
# ───────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestMigrationConsistency:

    def test_no_pending_migrations(self):
        """Verify model state matches migration state."""
        from django.core.management import call_command

        out = StringIO()
        try:
            call_command("makemigrations", "--check", "--dry-run", stdout=out)
        except SystemExit as exc:
            if exc.code != 0:
                pytest.fail(f"Pending migrations detected: {out.getvalue()}")
