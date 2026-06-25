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
        self.assertEqual(self.case.display_number, "Дело без номера")

    def test_display_number_uses_authority_number(self) -> None:
        self.case.authority_case_number = "WSC-II-P.6151.138285.2025"
        self.assertEqual(self.case.display_number, "WSC-II-P.6151.138285.2025")

    def test_display_number_ignores_internal_number(self) -> None:
        # internal_number is deprecated and must never surface to staff.
        self.case.internal_number = "INTERNAL-123"
        self.case.authority_case_number = ""
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


class CompatibilityHelperTests(TestCase):
    """spec section 4: legacy compatibility helper must never auto-create or
    silently pick from multiple cases."""

    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(assigned_staff=self.staff)

    def test_single_case_resolves(self) -> None:
        from clients.services.cases import get_legacy_compatibility_case

        case = self.client_obj.cases.get()
        resolved = get_legacy_compatibility_case(self.client_obj.pk, "Document")
        self.assertEqual(resolved.pk, case.pk)

    def test_multiple_cases_raise(self) -> None:
        from clients.services.cases import get_legacy_compatibility_case

        create_case_for_client(client=self.client_obj, actor=self.staff, application_purpose="study")
        with self.assertRaises(ValidationError):
            get_legacy_compatibility_case(self.client_obj.pk, "Document")
