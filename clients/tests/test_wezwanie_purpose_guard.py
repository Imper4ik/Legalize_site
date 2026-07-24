"""Wezwanie P/S/K purpose mapping must never wipe an existing case checklist.

Regression tests for the silent-checklist-wipe bug: OCR of a wezwanie with
status code "K" used to overwrite the case purpose with "family" without a
``family_role``, which resolves to an empty document checklist — nothing shows
as missing and missing-document reminder emails stop going out.
"""
from __future__ import annotations

from django.test import TestCase

from clients.models import Case
from clients.services.case_context import purpose_for_case
from clients.services.cases import create_case_for_client
from clients.services.document_workflow_wezwanie import (
    _apply_confirmation_updates,
    _apply_parsed_client_updates,
)
from clients.services.wezwanie_parser import WezwanieData
from clients.testing.factories import create_test_client, create_test_user


class WezwaniePurposeGuardTests(TestCase):
    def setUp(self) -> None:
        self.staff = create_test_user(role="Admin")
        self.client_obj = create_test_client(purpose="work")
        self.case = self.client_obj.cases.get()

    def test_parsed_k_code_does_not_overwrite_existing_purpose(self) -> None:
        parsed = WezwanieData(text="wezwanie", application_status_code="K")

        case_fields, _client_fields, auto_updates = _apply_parsed_client_updates(
            self.case, self.client_obj, parsed, actor=self.staff
        )

        self.assertNotIn("application_purpose", case_fields)
        self.assertEqual(self.case.application_purpose, "work")
        # Staff still learn about the mismatch instead of a silent no-op.
        self.assertTrue(any("work" in note for note in auto_updates))

    def test_parsed_k_code_does_not_set_roleless_family_on_empty_purpose(self) -> None:
        Case.all_objects.filter(pk=self.case.pk).update(application_purpose="")
        self.case.refresh_from_db()
        parsed = WezwanieData(text="wezwanie", application_status_code="K")

        case_fields, _client_fields, auto_updates = _apply_parsed_client_updates(
            self.case, self.client_obj, parsed, actor=self.staff
        )

        self.assertNotIn("application_purpose", case_fields)
        self.assertEqual(self.case.application_purpose, "")
        self.assertTrue(auto_updates)

    def test_parsed_s_code_still_fills_empty_purpose(self) -> None:
        Case.all_objects.filter(pk=self.case.pk).update(application_purpose="")
        self.case.refresh_from_db()
        parsed = WezwanieData(text="wezwanie", application_status_code="S")

        case_fields, _client_fields, _auto_updates = _apply_parsed_client_updates(
            self.case, self.client_obj, parsed, actor=self.staff
        )

        self.assertIn("application_purpose", case_fields)
        self.assertEqual(self.case.application_purpose, "study")

    def test_parsed_code_matching_existing_purpose_is_a_no_op(self) -> None:
        parsed = WezwanieData(text="wezwanie", application_status_code="P")

        case_fields, _client_fields, auto_updates = _apply_parsed_client_updates(
            self.case, self.client_obj, parsed, actor=self.staff
        )

        self.assertNotIn("application_purpose", case_fields)
        self.assertEqual(self.case.application_purpose, "work")
        self.assertFalse(any("purpose" in note.lower() for note in auto_updates))

    def test_confirmed_k_code_does_not_overwrite_existing_purpose(self) -> None:
        case_fields, _client_fields, _auto_updates = _apply_confirmation_updates(
            self.case,
            self.client_obj,
            {"application_status_code": "K"},
            actor=self.staff,
        )

        self.assertNotIn("application_purpose", case_fields)
        self.assertEqual(self.case.application_purpose, "work")

    def test_family_purpose_with_role_keeps_its_checklist(self) -> None:
        family_case = create_case_for_client(
            client=self.client_obj,
            actor=self.staff,
            application_purpose="family",
            family_role="family_spouse",
        )

        self.assertEqual(purpose_for_case(family_case), "family_spouse")
        checklist = family_case.get_document_checklist()
        self.assertTrue(any(row["is_required"] for row in checklist))

    def test_roleless_family_purpose_degrades_to_unset_not_empty_checklist(self) -> None:
        # Simulate legacy/bad data: Case.clean forbids this state, so write it
        # past validation the way the old OCR overwrite used to.
        Case.all_objects.filter(pk=self.case.pk).update(
            application_purpose="family", family_role=""
        )
        self.case.refresh_from_db()

        # "" forces callers into the explicit purpose-selection flow instead of
        # rendering a known purpose whose checklist is silently empty.
        self.assertEqual(purpose_for_case(self.case), "")
