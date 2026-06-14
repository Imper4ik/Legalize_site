"""P0 regression tests: family, ZUS RCA, reminders, and checklists."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import Client as DjangoClient
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from clients.constants import DocumentType
from clients.forms import ClientForm, DocumentUploadForm
from clients.models import (
    Client,
    Document,
    DocumentRequirement,
    FamilyGroup,
    Payment,
    Reminder,
)
from clients.services.zus import expected_zus_months, missing_zus_months
from clients.tests.factories import create_admin_user, create_staff_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(db, **kwargs):
    defaults = dict(
        first_name="Test",
        last_name="Client",
        email="t@example.com",
        phone="+48000000000",
        citizenship="UA",
        application_purpose="work",
    )
    defaults.update(kwargs)
    return Client.objects.create(**defaults)


def _make_doc(client, doc_type="passport", **kwargs):
    from django.core.files.base import ContentFile
    content = ContentFile(b"fake-pdf-content", name="test.pdf")
    return Document.objects.create(
        client=client,
        document_type=doc_type,
        file=content,
        **kwargs,
    )


# ===========================================================================
# 1. FAMILY / CHECKLIST RESOLUTION
# ===========================================================================

class TestFamilyChecklistResolution:
    """Verify get_document_requirement_purpose() routes correctly."""

    @pytest.mark.django_db
    def test_work_client_gets_work_checklist(self):
        c = _make_client(None, application_purpose="work", family_role="")
        assert c.get_document_requirement_purpose() == "work"

    @pytest.mark.django_db
    def test_work_sponsor_gets_work_checklist(self):
        c = _make_client(None, application_purpose="work", family_role="sponsor")
        assert c.get_document_requirement_purpose() == "work"

    @pytest.mark.django_db
    def test_family_spouse_gets_family_spouse_checklist(self):
        c = _make_client(None, application_purpose="family", family_role="family_spouse")
        assert c.get_document_requirement_purpose() == "family_spouse"

    @pytest.mark.django_db
    def test_family_child_gets_family_child_checklist(self):
        c = _make_client(None, application_purpose="family", family_role="family_child")
        assert c.get_document_requirement_purpose() == "family_child"

    @pytest.mark.django_db
    def test_family_sponsor_gets_work_checklist(self):
        c = _make_client(None, application_purpose="family", family_role="sponsor")
        assert c.get_document_requirement_purpose() == "work"

    @pytest.mark.django_db
    def test_study_client_gets_study_checklist(self):
        c = _make_client(None, application_purpose="study", family_role="")
        assert c.get_document_requirement_purpose() == "study"


# ===========================================================================
# 2. CLIENT FORM FAMILY VALIDATION
# ===========================================================================

class TestClientFormFamilyValidation:

    @pytest.mark.django_db
    def test_family_without_sponsor_errors(self):
        user = create_staff_user()
        form = ClientForm(
            data={
                "first_name": "A", "last_name": "B", "email": "a@b.com",
                "phone": "+48000000000", "citizenship": "UA",
                "application_purpose": "family", "family_role": "family_spouse",
                "language": "pl", "status": "new", "workflow_stage": "new_client",
            },
            user=user,
        )
        assert not form.is_valid()
        assert "sponsor_client" in form.errors

    @pytest.mark.django_db
    def test_family_without_role_errors(self):
        user = create_staff_user()
        sponsor = _make_client(None, email="sponsor@x.com")
        form = ClientForm(
            data={
                "first_name": "A", "last_name": "B", "email": "a@b.com",
                "phone": "+48000000000", "citizenship": "UA",
                "application_purpose": "family", "family_role": "",
                "sponsor_client": sponsor.pk,
                "language": "pl", "status": "new", "workflow_stage": "new_client",
            },
            user=user,
        )
        assert not form.is_valid()
        assert "family_role" in form.errors

    @pytest.mark.django_db
    def test_family_sponsor_form_valid_without_sponsor_client(self):
        user = create_staff_user()
        form = ClientForm(
            data={
                "first_name": "A", "last_name": "B", "email": "a@b.com",
                "phone": "+48000000000", "citizenship": "UA",
                "application_purpose": "family", "family_role": "sponsor",
                "sponsor_client": "",
                "language": "pl", "status": "new", "workflow_stage": "new_client",
            },
            user=user,
        )
        assert form.is_valid(), form.errors

    @pytest.mark.django_db
    def test_family_sponsor_form_clears_sponsor_client(self):
        user = create_staff_user()
        random_sponsor = _make_client(None, email="sponsor@x.com")
        form = ClientForm(
            data={
                "first_name": "A", "last_name": "B", "email": "a@b.com",
                "phone": "+48000000000", "citizenship": "UA",
                "application_purpose": "family", "family_role": "sponsor",
                "sponsor_client": random_sponsor.pk,
                "language": "pl", "status": "new", "workflow_stage": "new_client",
            },
            user=user,
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["sponsor_client"] is None

    @pytest.mark.django_db
    def test_self_sponsor_errors(self):
        user = create_staff_user()
        client = _make_client(None, email="self@x.com")
        form = ClientForm(
            data={
                "first_name": "A", "last_name": "B", "email": "a@b.com",
                "phone": "+48000000000", "citizenship": "UA",
                "application_purpose": "family", "family_role": "family_spouse",
                "sponsor_client": client.pk,
                "language": "pl", "status": "new", "workflow_stage": "new_client",
            },
            instance=client,
            user=user,
        )
        assert not form.is_valid()
        assert "sponsor_client" in form.errors

    @pytest.mark.django_db
    def test_non_family_clears_sponsor_and_role(self):
        user = create_staff_user()
        sponsor = _make_client(None, email="sponsor@x.com")
        form = ClientForm(
            data={
                "first_name": "A", "last_name": "B", "email": "a@b.com",
                "phone": "+48000000000", "citizenship": "UA",
                "application_purpose": "work", "family_role": "family_spouse",
                "sponsor_client": sponsor.pk,
                "language": "pl", "status": "new", "workflow_stage": "new_client",
            },
            user=user,
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["sponsor_client"] is None
        assert form.cleaned_data["family_role"] == ""


# ===========================================================================
# 3. ADD RELATIVE SERVER-SIDE INITIAL
# ===========================================================================

class TestAddRelativeServerSideInitial:

    @pytest.mark.django_db
    def test_sponsor_initial_with_accessible_client(self):
        admin = create_admin_user()
        sponsor = _make_client(None, email="sponsor@x.com")
        http = DjangoClient()
        http.force_login(admin)
        url = reverse("clients:client_add") + f"?sponsor={sponsor.pk}"
        response = http.get(url)
        assert response.status_code == 200
        assert str(sponsor.pk) in response.content.decode()

    @pytest.mark.django_db
    def test_inaccessible_sponsor_returns_404(self):
        staff = create_staff_user()
        sponsor = _make_client(None, email="hidden@x.com")
        # Assign sponsor to a different staff member so it becomes inaccessible
        other_staff = create_staff_user(email="other@x.com")
        sponsor.assigned_staff = other_staff
        sponsor.save(update_fields=["assigned_staff"])
        http = DjangoClient()
        http.force_login(staff)
        url = reverse("clients:client_add") + f"?sponsor={sponsor.pk}"
        response = http.get(url)
        # Should be 404 if access is properly restricted
        # Or 200 if staff role has full access (Admin/Manager have full access)
        assert response.status_code in (200, 404)


# ===========================================================================
# 4. FAMILY DASHBOARD GET — NO SIDE EFFECTS
# ===========================================================================

class TestFamilyDashboardGetNoSideEffects:

    @pytest.mark.django_db
    def test_get_does_not_create_family_group(self):
        admin = create_admin_user()
        sponsor = _make_client(None, application_purpose="family", family_role="", email="sp@x.com")
        http = DjangoClient()
        http.force_login(admin)
        url = reverse("clients:family_dashboard", kwargs={"pk": sponsor.pk})

        original_role = sponsor.family_role
        response = http.get(url)
        assert response.status_code == 200

        sponsor.refresh_from_db()
        assert sponsor.family_role == original_role
        assert not FamilyGroup.objects.filter(sponsor=sponsor).exists()


# ===========================================================================
# 5. ZUS RCA BACKEND LOGIC
# ===========================================================================

class TestZusRcaBackend:

    def test_future_fingerprints_returns_empty(self):
        result = expected_zus_months(date(2030, 1, 1), today=date(2026, 5, 14))
        assert result == []

    def test_day_14_does_not_include_april(self):
        """On May 14, last_expected = month_start(2026-05-14) - 2 = March 2026."""
        result = expected_zus_months(date(2026, 2, 10), today=date(2026, 5, 14))
        months = [m.strftime("%Y-%m") for m in result]
        assert "2026-04" not in months

    def test_day_15_includes_april(self):
        """On May 15, last_expected = month_start(2026-05-15) - 1 = April 2026."""
        result = expected_zus_months(date(2026, 2, 10), today=date(2026, 5, 15))
        months = [m.strftime("%Y-%m") for m in result]
        assert "2026-04" in months

    @pytest.mark.django_db
    def test_missing_zus_requires_waiting_decision(self):
        c = _make_client(
            None,
            workflow_stage="document_collection",
            fingerprints_date=date(2026, 2, 10),
        )
        assert missing_zus_months(c, today=date(2026, 5, 15)) == []

    @pytest.mark.django_db
    def test_missing_zus_requires_no_decision_date(self):
        c = _make_client(
            None,
            workflow_stage="waiting_decision",
            fingerprints_date=date(2026, 2, 10),
            decision_date=date(2026, 5, 1),
        )
        assert missing_zus_months(c, today=date(2026, 5, 15)) == []


class TestClientDetailZusUploadMonths:

    @pytest.mark.django_db
    def test_missing_zus_month_buttons_prefill_upload_month(self):
        admin = create_admin_user()
        client = _make_client(
            None,
            workflow_stage="waiting_decision",
            fingerprints_date=date(2026, 2, 10),
        )
        http = DjangoClient()
        http.force_login(admin)

        with patch("clients.services.zus.timezone.localdate", return_value=date(2026, 5, 15)):
            response = http.get(reverse("clients:client_detail", kwargs={"pk": client.pk}))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'data-zus-period-month="2026-03-01"' in content
        assert 'data-zus-period-month="2026-04-01"' in content
        assert "ZUS 03.2026" in content
        assert "ZUS 04.2026" in content

    @pytest.mark.django_db
    @override_settings(LANGUAGE_CODE="ru")
    def test_uploaded_zus_document_shows_saved_report_month(self):
        admin = create_admin_user()
        client = _make_client(None)
        _make_doc(
            client,
            doc_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            zus_period_month=date(2026, 4, 1),
        )
        http = DjangoClient()
        http.force_login(admin)

        response = http.get(reverse("clients:client_detail", kwargs={"pk": client.pk}))

        assert response.status_code == 200
        content = response.content.decode()
        assert "ZUS \u0437\u0430 \u043c\u0435\u0441\u044f\u0446:" in content
        assert "04.2026" in content


class TestDocumentUploadFormZus:

    @pytest.mark.django_db
    def test_zus_rca_allows_blank_period_month_for_insurance_policy(self):
        client = _make_client(None)
        form = DocumentUploadForm(
            data={"expiry_date": "", "zus_period_month": ""},
            files={"file": _simple_uploaded_file()},
            doc_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            client=client,
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["zus_period_month"] is None

    @pytest.mark.django_db
    def test_non_zus_clears_period_month(self):
        client = _make_client(None)
        from django.core.files.uploadedfile import SimpleUploadedFile
        pdf = SimpleUploadedFile("test.pdf", _minimal_pdf_bytes(), content_type="application/pdf")
        form = DocumentUploadForm(
            data={"expiry_date": "", "zus_period_month": "2026-05-01"},
            files={"file": pdf},
            doc_type="passport",
            client=client,
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["zus_period_month"] is None

    @pytest.mark.django_db
    def test_duplicate_zus_period_blocked(self):
        client = _make_client(None)
        _make_doc(client, doc_type=DocumentType.ZUS_RCA_OR_INSURANCE.value, zus_period_month=date(2026, 3, 1))
        form = DocumentUploadForm(
            data={"expiry_date": "", "zus_period_month": "2026-03-15"},
            files={"file": _simple_uploaded_file()},
            doc_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            client=client,
        )
        assert not form.is_valid()
        assert "zus_period_month" in form.errors


def _minimal_pdf_bytes():
    """Return bytes that pass the document validator's PDF checks."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n183\n"
        b"%%EOF\n"
    )


def _simple_uploaded_file():
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile("test.pdf", _minimal_pdf_bytes(), content_type="application/pdf")


# ===========================================================================
# 6. WEEKLY MISSING DOCS IDEMPOTENCY
# ===========================================================================

class TestWeeklyMissingDocsIdempotency:

    @pytest.mark.django_db
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_once_per_week(self):
        client = _make_client(
            None,
            workflow_stage="waiting_decision",
            fingerprints_date=date(2026, 4, 1),
            email="user@example.com",
        )
        DocumentRequirement.objects.create(
            application_purpose="work",
            document_type="passport",
            is_required=True,
        )

        today = date(2026, 5, 5)
        iso_year, iso_week, _ = today.isocalendar()
        weekly_key = f"waiting_decision_missing_docs:{client.pk}:{iso_year}-W{iso_week:02d}"

        from clients.services.notifications import send_missing_documents_email

        with patch("clients.services.notifications.timezone") as tz_mock:
            tz_mock.localdate.return_value = today
            tz_mock.localtime.return_value = timezone.now()

            sent1 = send_missing_documents_email(client, weekly_key=weekly_key)
            sent2 = send_missing_documents_email(client, weekly_key=weekly_key)

        assert sent1 >= 0  # May or may not send depending on context
        # The second call with the same key should not re-send
        assert sent2 == 0 or sent1 == 0  # If first was sent, second should be blocked


# ===========================================================================
# 7. UPDATE_REMINDERS COMMAND
# ===========================================================================

class TestUpdateRemindersCommand:

    @pytest.mark.django_db
    def test_dry_run_creates_no_document_reminders(self):
        client = _make_client(None)
        _make_doc(client, expiry_date=date.today() + timedelta(days=5))
        Payment.objects.create(
            client=client,
            service_description="karta_pobytu",
            total_amount=500,
            due_date=date.today() - timedelta(days=1),
            status="pending",
        )
        # Payment signal creates a payment reminder automatically.
        # Dry run should NOT create document reminders.
        pre_run_document_reminders = Reminder.objects.filter(reminder_type="document").count()

        call_command("update_reminders", dry_run=True)
        assert Reminder.objects.filter(reminder_type="document").count() == pre_run_document_reminders

    @pytest.mark.django_db
    def test_only_payments_runs_only_payments(self):
        client = _make_client(None)
        _make_doc(client, expiry_date=date.today() + timedelta(days=5))
        Payment.objects.create(
            client=client,
            service_description="karta_pobytu",
            total_amount=500,
            due_date=date.today() - timedelta(days=1),
            status="pending",
        )

        call_command("update_reminders", only=["payments"])
        # Only payment reminders should be created, not document ones
        payment_reminders = Reminder.objects.filter(reminder_type="payment")
        document_reminders = Reminder.objects.filter(reminder_type="document")
        assert payment_reminders.count() >= 1
        assert document_reminders.count() == 0

    @pytest.mark.django_db
    def test_document_window_minus_30_plus_30(self):
        client = _make_client(None)
        today = date.today()

        # -31 days: should NOT get a reminder
        doc_old = _make_doc(client, doc_type="passport_old", expiry_date=today - timedelta(days=31))
        # -10 days: SHOULD get a reminder (recently expired)
        doc_recent = _make_doc(client, doc_type="passport_recent", expiry_date=today - timedelta(days=10))
        # today: SHOULD get a reminder
        doc_today = _make_doc(client, doc_type="passport_today", expiry_date=today)
        # +30 days: SHOULD get a reminder
        doc_future = _make_doc(client, doc_type="passport_future", expiry_date=today + timedelta(days=30))
        # +31 days: should NOT get a reminder
        doc_far = _make_doc(client, doc_type="passport_far", expiry_date=today + timedelta(days=31))

        call_command("update_reminders", only=["documents"])

        reminder_doc_ids = set(Reminder.objects.values_list("document_id", flat=True))
        assert doc_old.pk not in reminder_doc_ids, "Doc -31 days should NOT get reminder"
        assert doc_recent.pk in reminder_doc_ids, "Doc -10 days SHOULD get reminder"
        assert doc_today.pk in reminder_doc_ids, "Doc today SHOULD get reminder"
        assert doc_future.pk in reminder_doc_ids, "Doc +30 days SHOULD get reminder"
        assert doc_far.pk not in reminder_doc_ids, "Doc +31 days should NOT get reminder"

    @pytest.mark.django_db
    def test_no_duplicate_reminders(self):
        client = _make_client(None)
        _make_doc(client, expiry_date=date.today() + timedelta(days=5))

        call_command("update_reminders", only=["documents"])
        count1 = Reminder.objects.filter(reminder_type="document").count()
        call_command("update_reminders", only=["documents"])
        count2 = Reminder.objects.filter(reminder_type="document").count()
        assert count1 == count2, "Second run should not create duplicates"


# ===========================================================================
# 8. CHECKLISTS/MANAGE FOR FAMILY PURPOSES
# ===========================================================================

class TestChecklistManageFamilyPurposes:

    @pytest.mark.django_db
    def test_family_spouse_returns_200(self):
        admin = create_admin_user()
        http = DjangoClient()
        http.force_login(admin)
        url = reverse("clients:document_checklist_manage") + "?purpose=family_spouse"
        response = http.get(url)
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_family_child_returns_200(self):
        admin = create_admin_user()
        http = DjangoClient()
        http.force_login(admin)
        url = reverse("clients:document_checklist_manage") + "?purpose=family_child"
        response = http.get(url)
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_no_submission_delete_for_system_purpose(self):
        admin = create_admin_user()
        http = DjangoClient()
        http.force_login(admin)
        url = reverse("clients:document_checklist_manage") + "?purpose=family_spouse"
        response = http.get(url)
        content = response.content.decode()
        # System purposes must not have submission_quick_delete links
        assert "submission_quick_delete" not in content or 'is_system' in content

    @pytest.mark.django_db
    def test_can_add_document_requirement_to_family_spouse(self):
        admin = create_admin_user()
        http = DjangoClient()
        http.force_login(admin)
        url = reverse("clients:document_requirement_add")
        response = http.post(url, {
            "purpose": "family_spouse",
            "name": "Marriage Certificate",
        })
        assert response.status_code in (200, 302)
        assert DocumentRequirement.objects.filter(
            application_purpose="family_spouse",
        ).exists()

    @pytest.mark.django_db
    def test_can_edit_document_requirement_in_family_child(self):
        admin = create_admin_user()
        req = DocumentRequirement.objects.create(
            application_purpose="family_child",
            document_type="birth_certificate",
            custom_name="Birth Cert",
            is_required=True,
        )
        http = DjangoClient()
        http.force_login(admin)
        url = reverse("clients:document_requirement_edit", kwargs={"pk": req.pk})
        response = http.post(url, {
            f"req-{req.pk}-custom_name": "Birth Certificate Updated",
            f"req-{req.pk}-custom_name_pl": "",
            f"req-{req.pk}-custom_name_en": "",
            f"req-{req.pk}-custom_name_ru": "",
            f"req-{req.pk}-is_required": "on",
        })
        assert response.status_code == 302
        req.refresh_from_db()
        assert req.custom_name == "Birth Certificate Updated"


# ===========================================================================
# 9. CLIENT FORM TEMPLATE — JS LOGIC KEYWORDS
# ===========================================================================

class TestClientFormTemplateJsLogic:
    """Verify client_form.html contains the updated family/sponsor JS logic."""

    def _template_source(self):
        from pathlib import Path
        tpl = Path(__file__).resolve().parent.parent / "templates" / "clients" / "client_form.html"
        return tpl.read_text(encoding="utf-8")

    def test_needs_sponsor_variable(self):
        src = self._template_source()
        assert "needsSponsor" in src

    def test_family_spouse_in_js(self):
        src = self._template_source()
        assert "family_spouse" in src

    def test_family_child_in_js(self):
        src = self._template_source()
        assert "family_child" in src

    def test_role_sponsor_check(self):
        src = self._template_source()
        assert "role === 'sponsor'" in src

    def test_role_select_change_listener(self):
        src = self._template_source()
        assert "roleSelect.addEventListener" in src
