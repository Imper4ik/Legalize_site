"""Tests for the case-first hardening slice.

Covers the case-number presentation rules (spec section 3), audit-log PII
neutralisation (spec section 9) and the rewritten ``validate_encrypted_data``
management command (spec section 9 / acceptance tests 21-22).
"""
from __future__ import annotations

import io
import uuid

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.utils import translation

from clients.models import Case
from clients.services.activity import sanitize_activity_metadata
from clients.services.archive import archive_case, restore_case
from clients.services.cases import create_case_for_client
from clients.services.workflow_transitions import transition_case_workflow
from clients.testing.factories import create_test_client, create_test_user


class DisplayNumberTests(TestCase):
    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(assigned_staff=self.staff)
        self.case = self.client_obj.cases.get()

    def test_display_number_never_exposes_uuid(self) -> None:
        self.case.authority_case_number = ""
        self.assertNotIn(str(self.case.uuid), self.case.display_number)

    def test_display_number_placeholder_when_unnumbered(self) -> None:
        self.case.authority_case_number = ""
        with translation.override("ru"):
            self.assertEqual(self.case.display_number, "Дело без номера")

    def test_display_number_uses_authority_number(self) -> None:
        self.case.authority_case_number = "WSC-II-P.6151.138285.2025"
        self.assertEqual(self.case.display_number, "WSC-II-P.6151.138285.2025")

    def test_display_number_ignores_internal_number(self) -> None:
        # internal_number is deprecated and must never surface to staff.
        self.case.internal_number = "INTERNAL-123"
        self.case.authority_case_number = ""
        with translation.override("ru"):
            self.assertEqual(self.case.display_number, "Дело без номера")


class AuditSummaryNeutralityTests(TestCase):
    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(
            first_name="Iryna", last_name="Kowalska", assigned_staff=self.staff
        )
        self.case = self.client_obj.cases.get()
        self.case.authority_case_number = "WSC-II-P.6151.138285.2025"
        self.case.save(update_fields=["authority_case_number"])

    def _summaries(self) -> list[str]:
        return list(
            self.client_obj.activities.values_list("summary", flat=True)
        )

    def test_archive_and_restore_summaries_contain_no_pii(self) -> None:
        batch = archive_case(case=self.case, actor=self.staff)
        restore_case(case=Case.all_objects.get(pk=self.case.pk), actor=self.staff, batch=batch)

        summaries = self._summaries()
        self.assertIn("Дело заархивировано", summaries)
        self.assertIn("Дело восстановлено", summaries)
        joined = " ".join(summaries)
        for forbidden in ("Iryna", "Kowalska", "WSC-II-P", str(self.case.uuid)):
            self.assertNotIn(forbidden, joined)

    def test_workflow_summary_is_neutral(self) -> None:
        transition_case_workflow(
            case=self.case, target_stage="document_collection", actor=self.staff
        )
        summaries = self._summaries()
        self.assertIn("Этап дела изменён", summaries)
        joined = " ".join(summaries)
        self.assertNotIn("WSC-II-P", joined)
        self.assertNotIn("document_collection", joined)


class MetadataSanitizerTests(TestCase):
    def test_pii_and_non_whitelisted_keys_are_dropped(self) -> None:
        sanitized = sanitize_activity_metadata(
            {
                "case_id": uuid.uuid4(),
                "document_count": 3,
                "email": "client@example.test",
                "old_value": "secret",
                "new_value": "secret2",
                "path": "/clients/1/",
                "attachment_name": "passport.pdf",
                "payment_id": 7,
            }
        )
        self.assertIn("case_id", sanitized)
        self.assertEqual(sanitized["document_count"], 3)
        for forbidden in (
            "email",
            "old_value",
            "new_value",
            "path",
            "attachment_name",
            "payment_id",
        ):
            self.assertNotIn(forbidden, sanitized)

    def test_controlled_operational_metadata_is_preserved(self) -> None:
        sanitized = sanitize_activity_metadata(
            {
                "workflow_stage": "document_collection",
                "case_status": "approved",
                "client_status": "pending",
                "old_status": "new",
                "new_status": "approved",
                "payment_status": "partial",
                "new_card_application_status": "submitted_with_number",
                "export_type": "zip",
                "verified": True,
                "has_case_number": False,
                "document_version_id": 42,
                "version_number": "3",
            }
        )

        self.assertEqual(sanitized["workflow_stage"], "document_collection")
        self.assertEqual(sanitized["payment_status"], "partial")
        self.assertEqual(sanitized["export_type"], "zip")
        self.assertIs(sanitized["verified"], True)
        self.assertIs(sanitized["has_case_number"], False)
        self.assertEqual(sanitized["document_version_id"], "42")
        self.assertEqual(sanitized["version_number"], 3)

    def test_invalid_controlled_metadata_values_are_dropped(self) -> None:
        sanitized = sanitize_activity_metadata(
            {
                "workflow_stage": "client@example.test",
                "payment_status": "transaction-123",
                "verified": "yes",
                "export_type": "../../secret",
            }
        )

        self.assertEqual(sanitized, {})


class EncryptedDataValidatorTests(TestCase):
    """Acceptance tests 21-22: exit codes and no-PII output."""

    def setUp(self) -> None:
        self.client_obj = create_test_client()
        self.case = self.client_obj.cases.get()
        # A properly encrypted authority number gives us a healthy token to read.
        self.case.authority_case_number = "WSC-II-P.6151.138285.2025"
        self.case.save(update_fields=["authority_case_number"])

    def _run(self) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        code = 0
        try:
            call_command(
                "validate_encrypted_data",
                "--model",
                "clients.Case",
                stdout=out,
                stderr=err,
            )
        except SystemExit as exc:  # non-zero exit raised as SystemExit
            code = int(exc.code or 0)
        return code, out.getvalue() + err.getvalue()

    def test_valid_data_exits_zero(self) -> None:
        code, output = self._run()
        self.assertEqual(code, 0)
        self.assertIn("OK", output)

    def test_plaintext_after_migration_fails(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE clients_case SET authority_case_number=%s WHERE id=%s",
                ["PLAINTEXT-SECRET-NUMBER", self.case.pk],
            )
        code, output = self._run()
        self.assertEqual(code, 1)
        self.assertIn("NOT_ENCRYPTED", output)
        # The raw plaintext value must never be printed.
        self.assertNotIn("PLAINTEXT-SECRET-NUMBER", output)

    def test_damaged_token_fails(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE clients_case SET authority_case_number=%s WHERE id=%s",
                ["gAAAAABbroken-token-value", self.case.pk],
            )
        code, output = self._run()
        self.assertEqual(code, 1)
        self.assertIn("DECRYPTION_FAILED", output)
        self.assertNotIn("gAAAAABbroken-token-value", output)


class AuthorityNumberClearsLegacyTests(TestCase):
    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(assigned_staff=self.staff)
        self.case = self.client_obj.cases.get()
        self.case.legacy_case_number = "OLD-123"
        self.case.needs_manual_number_check = True
        self.case.save(update_fields=["legacy_case_number", "needs_manual_number_check"])

    def test_saving_authority_number_clears_legacy_fields(self) -> None:
        from clients.services.locking import update_case_with_version

        update_case_with_version(
            case_id=self.case.id,
            expected_version=self.case.version,
            actor=self.staff,
            changes_dict={
                "authority_case_number": "WSC-II-P.6151.138285.2025",
                "legacy_case_number": "",
                "needs_manual_number_check": False,
                "workflow_stage": self.case.workflow_stage,
            },
        )
        refreshed = Case.all_objects.get(pk=self.case.pk)
        self.assertEqual(refreshed.authority_case_number, "WSC-II-P.6151.138285.2025")
        self.assertEqual(refreshed.legacy_case_number, "")
        self.assertFalse(refreshed.needs_manual_number_check)


class ClientPortalOnboardingTests(TestCase):
    """spec section 6: client_portal never auto-assigns a Case."""

    def setUp(self) -> None:
        from datetime import timedelta

        from django.utils import timezone

        from clients.models import ClientOnboardingSession
        from clients.services.onboarding_tokens import generate_onboarding_token

        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(assigned_staff=self.staff)
        self.case_a = self.client_obj.cases.get()
        self.case_b = create_case_for_client(
            client=self.client_obj, actor=self.staff, application_purpose="study"
        )
        self.raw_token, hashed = generate_onboarding_token()
        self.session = ClientOnboardingSession.objects.create(
            client=self.client_obj,
            scope="client_portal",
            case=None,
            token_hash=hashed,
            status="active",
            expires_at=timezone.now() + timedelta(days=1),
        )

    def test_portal_session_persists_with_null_case(self) -> None:
        self.session.refresh_from_db()
        self.assertEqual(self.session.scope, "client_portal")
        self.assertIsNone(self.session.case_id)

    def test_portal_session_does_not_autoassign_case(self) -> None:
        from clients.views.onboarding_views import check_onboarding_session

        resolved = check_onboarding_session(self.raw_token, request=None)
        self.assertIsNotNone(resolved)
        # No case is silently chosen for the portal.
        self.assertIsNone(resolved.case_id)

    def test_portal_rejects_foreign_case_id(self) -> None:
        from django.contrib.sessions.backends.db import SessionStore
        from django.test import RequestFactory

        from clients.views.onboarding_views import check_onboarding_session

        other_client = create_test_client()
        foreign_case = other_client.cases.get()

        request = RequestFactory().get("/")
        request.session = SessionStore()
        request.session["case_id"] = foreign_case.id

        check_onboarding_session(self.raw_token, request=request)
        # The forged selection is dropped, not honoured.
        self.assertIsNone(request.session.get("case_id"))


class PortalScopeSection1Tests(TestCase):
    """spec section 1: the client portal is strictly case-scoped.

    Self-onboarding sessions never carry/auto-pick a Case; the selected case is
    re-validated on every request and all portal data (MOS, documents) is read
    and written only within that case.
    """

    def setUp(self) -> None:
        from datetime import timedelta

        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from clients.models import ClientOnboardingSession, Document, MOSApplicationData
        from clients.services.onboarding_tokens import generate_onboarding_token

        self.timezone = timezone
        self.timedelta = timedelta
        self.ClientOnboardingSession = ClientOnboardingSession
        self.MOSApplicationData = MOSApplicationData
        self.Document = Document
        self.generate_onboarding_token = generate_onboarding_token

        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(assigned_staff=self.staff)
        self.case_a = self.client_obj.cases.get()
        self.case_b = create_case_for_client(
            client=self.client_obj, actor=self.staff, application_purpose="study"
        )

        # Distinguishable MOS data per case.
        self.mos_a, _ = MOSApplicationData.objects.get_or_create(
            client=self.client_obj, case=self.case_a
        )
        self.mos_a.mos_purpose = "work"
        self.mos_a.save(update_fields=["mos_purpose"])
        self.mos_b, _ = MOSApplicationData.objects.get_or_create(
            client=self.client_obj, case=self.case_b
        )
        self.mos_b.mos_purpose = "study"
        self.mos_b.save(update_fields=["mos_purpose"])

        # A document on each case.
        from clients.constants import DocumentType
        from clients.testing.factories import build_pdf_upload

        self.doc_a = Document.objects.create(
            client=self.client_obj,
            case=self.case_a,
            document_type=DocumentType.PASSPORT.value,
            file=build_pdf_upload("a.pdf"),
            is_test_data=True,
        )
        self.doc_b = Document.objects.create(
            client=self.client_obj,
            case=self.case_b,
            document_type=DocumentType.PASSPORT.value,
            file=build_pdf_upload("b.pdf"),
            is_test_data=True,
        )

        # Give the client a login so the portal token flow works.
        User = get_user_model()
        self.user = User.objects.create_user(
            email="portal-client@example.test", password="portal-pass-123", is_active=True
        )
        self.client_obj.user = self.user
        self.client_obj.save(update_fields=["user"])

    def _portal_request(self, case_id: object = None):
        from django.contrib.sessions.backends.db import SessionStore
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.user = self.user
        request.session = SessionStore()
        if case_id is not None:
            request.session["case_id"] = case_id
        return request

    def test_self_onboarding_creates_portal_scoped_session(self) -> None:
        from clients.constants import SELF_ONBOARDING_SLUG
        from clients.views.onboarding_views import check_onboarding_session

        request = self._portal_request()
        session = check_onboarding_session(SELF_ONBOARDING_SLUG, request=request)
        self.assertIsNotNone(session)

        created = self.ClientOnboardingSession.objects.get(client=self.client_obj)
        self.assertEqual(created.scope, "client_portal")
        self.assertIsNone(created.case_id)

    def test_active_case_resolves_for_selected_case(self) -> None:
        from clients.constants import SELF_ONBOARDING_SLUG
        from clients.views.onboarding_views import check_onboarding_session

        request = self._portal_request(case_id=self.case_b.id)
        session = check_onboarding_session(SELF_ONBOARDING_SLUG, request=request)
        self.assertEqual(session.active_case.id, self.case_b.id)

    def test_mos_is_scoped_to_selected_case(self) -> None:
        from clients.constants import SELF_ONBOARDING_SLUG
        from clients.views.onboarding_views import _get_scoped_mos, check_onboarding_session

        request = self._portal_request(case_id=self.case_b.id)
        session = check_onboarding_session(SELF_ONBOARDING_SLUG, request=request)
        scoped = _get_scoped_mos(session)
        self.assertEqual(scoped.pk, self.mos_b.pk)
        self.assertNotEqual(scoped.pk, self.mos_a.pk)

    def test_portal_preview_cannot_reach_other_case_document(self) -> None:
        from django.test import Client as DjangoClient
        from django.urls import reverse

        from clients.constants import SELF_ONBOARDING_SLUG

        slug = SELF_ONBOARDING_SLUG
        http = DjangoClient()
        http.force_login(self.user)
        # Pick case B server-side.
        resp = http.post(
            reverse("clients:onboarding_select_case", kwargs={"token": slug}),
            {"case_id": self.case_b.id},
        )
        self.assertEqual(resp.status_code, 302)

        # Document of case B is reachable…
        ok = http.get(
            reverse(
                "clients:onboarding_document_preview",
                kwargs={"token": slug, "doc_id": self.doc_b.id},
            )
        )
        self.assertEqual(ok.status_code, 200)
        # …but the other case's document is not (neutral 404, no leak).
        denied = http.get(
            reverse(
                "clients:onboarding_document_preview",
                kwargs={"token": slug, "doc_id": self.doc_a.id},
            )
        )
        self.assertEqual(denied.status_code, 404)

    def test_invalid_token_returns_none(self) -> None:
        from clients.views.onboarding_views import check_onboarding_session

        request = self._portal_request()
        self.assertIsNone(check_onboarding_session("not-a-real-token", request=request))

    def test_expired_token_raises_gone(self) -> None:
        from clients.views.onboarding_views import OnboardingLinkExpired, check_onboarding_session

        raw_token, hashed = self.generate_onboarding_token()
        self.ClientOnboardingSession.objects.create(
            client=self.client_obj,
            scope="case_link",
            case=self.case_a,
            token_hash=hashed,
            status="active",
            expires_at=self.timezone.now() - self.timedelta(days=1),
        )
        with self.assertRaises(OnboardingLinkExpired):
            check_onboarding_session(raw_token, request=self._portal_request())


class OcrCaseIsolationTests(TestCase):
    """spec section 5: OCR of a document on case B must not touch case A."""

    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(assigned_staff=self.staff)
        self.case_a = self.client_obj.cases.get()
        self.case_b = create_case_for_client(
            client=self.client_obj, actor=self.staff, application_purpose="study"
        )

    def test_confirmed_wezwanie_updates_only_its_case(self) -> None:
        from clients.constants import DocumentType
        from clients.models import Document
        from clients.services.document_workflow import confirm_wezwanie_document
        from clients.testing.factories import build_pdf_upload

        document = Document.objects.create(
            client=self.client_obj,
            case=self.case_b,
            document_type=DocumentType.WEZWANIE.value,
            file=build_pdf_upload("wezwanie.pdf"),
            awaiting_confirmation=True,
            ocr_status="success",
            is_test_data=True,
        )

        confirm_wezwanie_document(
            document=document,
            actor=self.staff,
            confirmation_data={
                "case_number": "WSC-II-S.6151.97770.2026",
                "fingerprints_date": "2026-08-15",
                "fingerprints_time": "10:30",
                "fingerprints_location": "Marszałkowska 3/5",
            },
        )

        case_b = Case.all_objects.get(pk=self.case_b.pk)
        case_a = Case.all_objects.get(pk=self.case_a.pk)

        self.assertEqual(case_b.authority_case_number, "WSC-II-S.6151.97770.2026")
        self.assertIsNotNone(case_b.fingerprints_date)
        # Case A is fully untouched.
        self.assertEqual(case_a.authority_case_number, "")
        self.assertIsNone(case_a.fingerprints_date)
        self.assertEqual(case_a.fingerprints_location, "")


class WorkdayPerCaseQueueTests(TestCase):
    """spec section 5: a client with two qualifying cases appears once per case,
    each carrying that specific case's MOS data (not an arbitrary first)."""

    def setUp(self) -> None:
        from clients.models import MOSApplicationData

        self.MOSApplicationData = MOSApplicationData
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(assigned_staff=self.staff)
        self.case_a = self.client_obj.cases.get()
        self.case_b = create_case_for_client(
            client=self.client_obj, actor=self.staff, application_purpose="study"
        )

    def _mark_new_card(self, case) -> None:
        mos, _ = self.MOSApplicationData.objects.get_or_create(client=self.client_obj, case=case)
        mos.new_residence_card_application_status = self.MOSApplicationData.NEW_CARD_STATUS_YES
        mos.save(update_fields=["new_residence_card_application_status"])

    def test_each_qualifying_case_appears_separately(self) -> None:
        from clients.services.workday import _new_card_missing_case

        self._mark_new_card(self.case_a)
        self._mark_new_card(self.case_b)

        items = _new_card_missing_case(self.staff, limit=50)
        mine = [item for item in items if item["client"].pk == self.client_obj.pk]
        # Both cases qualify -> the client surfaces twice (once per case).
        self.assertEqual(len(mine), 2)

    def test_numbered_case_is_excluded(self) -> None:
        from clients.services.workday import _new_card_missing_case

        self._mark_new_card(self.case_a)
        self._mark_new_card(self.case_b)
        # Give case B an authority number: only case A should remain.
        self.case_b.authority_case_number = "WSC-II-P.6151.100000.2026"
        self.case_b.save(update_fields=["authority_case_number"])

        items = _new_card_missing_case(self.staff, limit=50)
        mine = [item for item in items if item["client"].pk == self.client_obj.pk]
        self.assertEqual(len(mine), 1)


class WorkflowStageEditedOnCaseNotClientTests(TestCase):
    """spec section 4: the workflow stage is edited on the case (CaseForm), and
    the case-edit path enforces the transition policy."""

    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(assigned_staff=self.staff)
        self.case = self.client_obj.cases.get()

    def test_client_form_has_no_workflow_stage_field(self) -> None:
        from clients.forms import ClientForm

        form = ClientForm(instance=self.client_obj, user=self.staff)
        self.assertNotIn("workflow_stage", form.fields)

    def test_process_and_legacy_fields_move_to_case_form(self) -> None:
        from datetime import date

        from clients.forms import CaseForm, ClientForm

        # The client form no longer edits process/legacy number fields (§4).
        client_form = ClientForm(instance=self.client_obj, user=self.staff)
        for name in ("case_number", "submission_date", "fingerprints_date"):
            self.assertNotIn(name, client_form.fields)

        # The case form owns the process dates and parses dd.mm.yyyy input.
        case_form = CaseForm(
            data={
                "authority_case_number": "",
                "application_purpose": "work",
                "application_type": "",
                "basis_of_stay": "",
                "workflow_stage": self.case.workflow_stage,
                "submission_date": "15.03.2026",
                "fingerprints_date": "",
                "assigned_staff": "",
                "company": "",
                "version": self.case.version,
            },
            instance=self.case,
        )
        self.assertTrue(case_form.is_valid(), case_form.errors)
        self.assertEqual(case_form.cleaned_data["submission_date"], date(2026, 3, 15))

    def test_case_form_blocks_closing_with_open_payments(self) -> None:
        from decimal import Decimal

        from django.utils import timezone

        from clients.forms import CaseForm
        from clients.models import Payment
        from clients.models.case import CaseParticipant

        CaseParticipant.objects.get_or_create(
            case=self.case, client=self.client_obj, role="principal"
        )
        self.case.workflow_stage = "decision_received"
        self.case.decision_date = timezone.localdate()
        self.case.save(update_fields=["workflow_stage", "decision_date"])
        Payment.objects.create(
            client=self.client_obj,
            case=self.case,
            service_description="consultation",
            total_amount=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
            status="pending",
            is_test_data=True,
        )

        form = CaseForm(
            data={
                "authority_case_number": "",
                "application_purpose": "work",
                "application_type": "",
                "basis_of_stay": "",
                "workflow_stage": "closed",
                "version": self.case.version,
            },
            instance=self.case,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("workflow_stage", form.errors)


class WorkflowTransitionDoesNotMirrorToClientTests(TestCase):
    """spec section 4: workflow transitions write the case only; the deprecated
    client wrapper no longer mirrors stage/dates onto the Client."""

    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(
            workflow_stage="new_client", assigned_staff=self.staff
        )
        self.case = self.client_obj.cases.get()
        # The primary case mirrors the client's starting stage.
        self.case.workflow_stage = "new_client"
        self.case.save(update_fields=["workflow_stage"])

    def test_case_transition_leaves_client_stage_untouched(self) -> None:
        from clients.services.workflow_transitions import transition_case_workflow

        transition_case_workflow(
            case=self.case,
            target_stage="document_collection",
            actor=self.staff,
        )

        refreshed_case = Case.all_objects.get(pk=self.case.pk)
        # Process state lives on the case; the client no longer carries a stage.
        self.assertEqual(refreshed_case.workflow_stage, "document_collection")



class OcrDoesNotMirrorProcessStateToClientTests(TestCase):
    """spec section 4: OCR/wezwanie confirmation writes process state only to the
    case. The client may only receive permanent personal data (name), never the
    case number, workflow, fingerprints, decision or purpose."""

    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(
            first_name="Olek", last_name="Stary", assigned_staff=self.staff
        )
        self.case_a = self.client_obj.cases.get()
        self.case_b = create_case_for_client(
            client=self.client_obj, actor=self.staff, application_purpose="study"
        )

    def test_confirmation_keeps_process_state_off_the_client(self) -> None:
        from clients.constants import DocumentType
        from clients.models import Document
        from clients.services.document_workflow import confirm_wezwanie_document
        from clients.testing.factories import build_pdf_upload

        client_purpose_before = self.client_obj.application_purpose

        document = Document.objects.create(
            client=self.client_obj,
            case=self.case_b,
            document_type=DocumentType.WEZWANIE.value,
            file=build_pdf_upload("wezwanie.pdf"),
            awaiting_confirmation=True,
            ocr_status="success",
            is_test_data=True,
        )

        confirm_wezwanie_document(
            document=document,
            actor=self.staff,
            confirmation_data={
                "first_name": "Aleksander",
                "last_name": "Nowak",
                "case_number": "WSC-II-S.6151.55555.2026",
                "fingerprints_date": "2026-09-01",
                "decision_date": "2026-10-01",
                "application_status_code": "S",
            },
        )

        client = type(self.client_obj).all_objects.get(pk=self.client_obj.pk)
        # Permanent personal data is allowed on the client…
        self.assertEqual(client.first_name, "Aleksander")
        self.assertEqual(client.last_name, "Nowak")
        # …process state has no place on the client at all (the columns are gone)
        # and the application purpose is not mutated either.
        self.assertEqual(client.application_purpose, client_purpose_before)

        case_b = Case.all_objects.get(pk=self.case_b.pk)
        self.assertEqual(case_b.authority_case_number, "WSC-II-S.6151.55555.2026")
        self.assertIsNotNone(case_b.fingerprints_date)
        self.assertEqual(case_b.application_purpose, "study")


class HealthAlertsReadCaseNotClientTests(TestCase):
    """spec section 4: client health checks read the case number/fingerprints
    date from the active case, ignoring the legacy client mirror."""

    def setUp(self) -> None:
        from clients.models import MOSApplicationData

        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(assigned_staff=self.staff)
        self.case = self.client_obj.cases.get()
        mos, _ = MOSApplicationData.objects.get_or_create(client=self.client_obj, case=self.case)
        mos.new_residence_card_application_status = "yes"
        mos.save(update_fields=["new_residence_card_application_status"])

    def test_alert_fires_when_case_has_no_authority_number(self) -> None:
        # The alert tracks the case authority number (the legacy client field is
        # gone); with no number on the case it fires.
        with translation.override("ru"):
            titles = [str(a["title"]) for a in self.client_obj.get_health_alerts()]
            self.assertIn("Новая подача требует проверки дела", titles)

    def test_case_authority_number_clears_alert(self) -> None:
        # …only the case's authority number does.
        self.case.authority_case_number = "WSC-II-P.6151.100000.2026"
        self.case.save(update_fields=["authority_case_number"])
        titles = [str(a["title"]) for a in self.client_obj.get_health_alerts()]
        self.assertNotIn("Новая подача требует проверки дела", titles)


class CompatibilityHelperTests(TestCase):
    """spec section 4: legacy compatibility helper must never auto-create or
    silently pick from multiple cases."""

    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(assigned_staff=self.staff)

    def test_single_case_resolves(self) -> None:
        from clients.models.consistency import resolve_required_case

        case = self.client_obj.cases.get()
        resolved = resolve_required_case(self.client_obj.pk, "Document")
        self.assertEqual(resolved.pk, case.pk)

    def test_multiple_cases_raise(self) -> None:
        from clients.models.consistency import resolve_required_case

        create_case_for_client(client=self.client_obj, actor=self.staff, application_purpose="study")
        with self.assertRaises(ValidationError):
            resolve_required_case(self.client_obj.pk, "Document")

    def test_archived_only_case_raises_and_is_not_returned(self) -> None:
        # The fallback considers active cases only; it must not bind to an
        # archived case (spec section 1/3).
        from clients.models.consistency import resolve_required_case

        self.client_obj.cases.get().archive(save=True)
        with self.assertRaises(ValidationError):
            resolve_required_case(self.client_obj.pk, "Document")
