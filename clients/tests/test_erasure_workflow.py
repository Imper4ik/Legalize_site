"""RODO art. 17 erasure approval workflow: request → approve/reject → fulfil,
with a legal hold that blocks approval and automatic retention.
"""
from __future__ import annotations

from django.test import TestCase

from clients.models import Client
from clients.services.erasure import (
    ErasureWorkflowError,
    LegalHoldError,
    approve_erasure,
    place_legal_hold,
    reject_erasure,
    release_legal_hold,
    request_erasure,
)
from clients.testing.factories import create_test_client


class ErasureWorkflowTests(TestCase):
    def setUp(self) -> None:
        self.client_obj = create_test_client(first_name="Flow", last_name="Test")

    def test_request_sets_status_and_timestamp(self) -> None:
        request_erasure(self.client_obj)
        self.client_obj.refresh_from_db()
        self.assertEqual(self.client_obj.erasure_status, Client.ErasureStatus.REQUESTED)
        self.assertIsNotNone(self.client_obj.erasure_requested_at)

    def test_approve_moves_to_approved_with_audit(self) -> None:
        request_erasure(self.client_obj)
        approve_erasure(self.client_obj, actor=None, reason="identity verified")
        self.client_obj.refresh_from_db()
        self.assertEqual(self.client_obj.erasure_status, Client.ErasureStatus.APPROVED)
        self.assertIsNotNone(self.client_obj.erasure_approved_at)
        self.assertEqual(self.client_obj.erasure_decision_reason, "identity verified")

    def test_cannot_approve_without_request(self) -> None:
        with self.assertRaises(ErasureWorkflowError):
            approve_erasure(self.client_obj, actor=None, reason="x")

    def test_legal_hold_blocks_approval(self) -> None:
        request_erasure(self.client_obj)
        place_legal_hold(self.client_obj, reason="active case")
        with self.assertRaises(LegalHoldError):
            approve_erasure(self.client_obj, actor=None, reason="x")

    def test_release_hold_then_approve(self) -> None:
        request_erasure(self.client_obj)
        place_legal_hold(self.client_obj, reason="active case")
        release_legal_hold(self.client_obj)
        approve_erasure(self.client_obj, actor=None, reason="ok")
        self.client_obj.refresh_from_db()
        self.assertEqual(self.client_obj.erasure_status, Client.ErasureStatus.APPROVED)

    def test_reject_requires_reason(self) -> None:
        request_erasure(self.client_obj)
        with self.assertRaises(ErasureWorkflowError):
            reject_erasure(self.client_obj, actor=None, reason="   ")

    def test_reject_records_decision(self) -> None:
        request_erasure(self.client_obj)
        reject_erasure(self.client_obj, actor=None, reason="retention obligation")
        self.client_obj.refresh_from_db()
        self.assertEqual(self.client_obj.erasure_status, Client.ErasureStatus.REJECTED)
        self.assertEqual(self.client_obj.erasure_decision_reason, "retention obligation")

    def test_rejected_request_can_be_reopened(self) -> None:
        request_erasure(self.client_obj)
        reject_erasure(self.client_obj, actor=None, reason="not now")
        request_erasure(self.client_obj)
        self.client_obj.refresh_from_db()
        self.assertEqual(self.client_obj.erasure_status, Client.ErasureStatus.REQUESTED)
