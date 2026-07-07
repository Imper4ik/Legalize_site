"""ConsentRecord is an enforced append-only, tamper-evident audit log.

These tests pin the integrity guarantees that make it usable as art. 7(1) RODO
evidence: rows cannot be modified or deleted, and the per-client hash chain
detects any tampering, deletion, or reordering after the fact.
"""
from __future__ import annotations

from django.test import TestCase

from clients.models import ConsentRecord
from clients.testing.factories import create_test_client


class ConsentChainTests(TestCase):
    def setUp(self) -> None:
        self.client_obj = create_test_client(first_name="Con", last_name="Sent")

    def _grant(self, purpose: str, granted: bool = True) -> ConsentRecord:
        return ConsentRecord.record(
            client=self.client_obj,
            purpose=purpose,
            granted=granted,
            policy_version="2026-01",
        )

    def test_first_row_has_hash_and_empty_prev(self) -> None:
        row = self._grant(ConsentRecord.Purpose.DATA_PROCESSING)
        self.assertEqual(row.prev_hash, "")
        self.assertTrue(row.entry_hash)

    def test_chain_links_successive_rows(self) -> None:
        first = self._grant(ConsentRecord.Purpose.DATA_PROCESSING)
        second = self._grant(ConsentRecord.Purpose.MARKETING)
        self.assertEqual(second.prev_hash, first.entry_hash)

        ok, bad = ConsentRecord.verify_chain(self.client_obj)
        self.assertTrue(ok)
        self.assertIsNone(bad)

    def test_verify_detects_field_tampering(self) -> None:
        row = self._grant(ConsentRecord.Purpose.MARKETING, granted=True)
        # Flip the stored decision directly in the DB, bypassing save().
        ConsentRecord.objects.filter(pk=row.pk).update(granted=False)

        ok, bad = ConsentRecord.verify_chain(self.client_obj)
        self.assertFalse(ok)
        self.assertIsNotNone(bad)
        self.assertEqual(bad.pk, row.pk)

    def test_verify_detects_deleted_row(self) -> None:
        self._grant(ConsentRecord.Purpose.DATA_PROCESSING)
        middle = self._grant(ConsentRecord.Purpose.SERVICE_PROVISION)
        self._grant(ConsentRecord.Purpose.MARKETING)
        # Hard-delete the middle row at the DB level, breaking the chain.
        ConsentRecord.objects.filter(pk=middle.pk).delete()

        ok, _bad = ConsentRecord.verify_chain(self.client_obj)
        self.assertFalse(ok)

    def test_save_on_existing_row_is_forbidden(self) -> None:
        row = self._grant(ConsentRecord.Purpose.DATA_PROCESSING)
        row.granted = False
        with self.assertRaises(ValueError):
            row.save()

    def test_delete_is_forbidden(self) -> None:
        row = self._grant(ConsentRecord.Purpose.DATA_PROCESSING)
        with self.assertRaises(ValueError):
            row.delete()

    def test_state_helpers_still_reflect_latest(self) -> None:
        self._grant(ConsentRecord.Purpose.MARKETING, granted=True)
        self._grant(ConsentRecord.Purpose.MARKETING, granted=False)
        self.assertFalse(
            ConsentRecord.is_granted(self.client_obj, ConsentRecord.Purpose.MARKETING)
        )
