from __future__ import annotations

import io
import json
from contextlib import contextmanager
from typing import Iterator
from unittest.mock import patch

from cryptography.fernet import Fernet, InvalidToken
from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, models, transaction
from django.test import TestCase, override_settings

from clients.constants import DocumentType
from clients.models import Case, Document
from clients.testing.factories import create_test_client
from fernet_fields import EncryptedJSONField, EncryptedTextField
from fernet_fields.fields import ENCRYPTED_VALUE_UNAVAILABLE


class FernetRotationCommandTests(TestCase):
    def setUp(self) -> None:
        self.old_key = Fernet.generate_key().decode("ascii")
        self.new_key = Fernet.generate_key().decode("ascii")
        self._clear_fernet_caches()

    def tearDown(self) -> None:
        self._clear_fernet_caches()

    @staticmethod
    def _clear_fernet_caches() -> None:
        # Encrypted fields use cached_property for their keyring. Tests replace
        # FERNET_KEYS at runtime, so both sides of every override must evict it.
        for model in apps.get_models():
            for field in model._meta.get_fields():
                if isinstance(field, (EncryptedTextField, EncryptedJSONField)):
                    field.__dict__.pop("_fernet", None)

    @contextmanager
    def _keyring(self, *keys: str) -> Iterator[None]:
        with override_settings(FERNET_KEYS=list(keys)):
            self._clear_fernet_caches()
            try:
                yield
            finally:
                self._clear_fernet_caches()

    @staticmethod
    def _raw_value(model: type[models.Model], field_name: str, pk: object) -> str:
        field = model._meta.get_field(field_name)
        pk_field = model._meta.pk
        assert pk_field is not None
        quote = connection.ops.quote_name
        query = (
            f"SELECT {quote(str(field.column))} FROM {quote(model._meta.db_table)} "
            f"WHERE {quote(str(pk_field.column))} = %s"
        )
        with connection.cursor() as cursor:
            cursor.execute(query, [pk])
            row = cursor.fetchone()
        if row is None:
            raise AssertionError("Encrypted test row was not found.")
        return str(row[0])

    @staticmethod
    def _set_raw_value(
        model: type[models.Model],
        field_name: str,
        pk: object,
        raw_value: str,
    ) -> None:
        field = model._meta.get_field(field_name)
        pk_field = model._meta.pk
        assert pk_field is not None
        quote = connection.ops.quote_name
        query = (
            f"UPDATE {quote(model._meta.db_table)} SET {quote(str(field.column))} = %s "
            f"WHERE {quote(str(pk_field.column))} = %s"
        )
        with connection.cursor() as cursor:
            cursor.execute(query, [raw_value, pk])

    @staticmethod
    def _run_validator(model_label: str, *, primary_key_only: bool) -> tuple[int, str]:
        args = ["--model", model_label]
        if primary_key_only:
            args.append("--primary-key-only")
        stdout = io.StringIO()
        stderr = io.StringIO()
        exit_code = 0
        try:
            call_command(
                "validate_encrypted_data",
                *args,
                stdout=stdout,
                stderr=stderr,
            )
        except SystemExit as exc:
            exit_code = int(exc.code or 0)
        return exit_code, stdout.getvalue() + stderr.getvalue()

    def _create_document(self, parsed_data: dict[str, object]) -> Document:
        client = create_test_client()
        case = client.cases.get()
        return Document.objects.create(
            client=client,
            case=case,
            document_type=DocumentType.PASSPORT.value,
            file="",
            parsed_data=parsed_data,
            is_test_data=True,
        )

    def test_json_rotation_reencrypts_with_primary_key(self) -> None:
        payload = {"status": "review", "secret": "json-rotation-secret"}
        with self._keyring(self.old_key):
            document = self._create_document(payload)
            before = self._raw_value(Document, "parsed_data", document.pk)
            self.assertEqual(
                json.loads(Fernet(self.old_key).decrypt(before.encode()).decode()),
                payload,
            )

        stdout = io.StringIO()
        stderr = io.StringIO()
        with self._keyring(self.new_key, self.old_key):
            call_command(
                "rotate_fernet_fields",
                "--model",
                "clients.Document",
                "--maintenance-confirmed",
                stdout=stdout,
                stderr=stderr,
            )
            after = self._raw_value(Document, "parsed_data", document.pk)

        self.assertNotEqual(after, before)
        self.assertEqual(
            json.loads(Fernet(self.new_key).decrypt(after.encode()).decode()),
            payload,
        )
        with self.assertRaises(InvalidToken):
            Fernet(self.old_key).decrypt(after.encode())
        output = stdout.getvalue() + stderr.getvalue()
        self.assertIn("Rotated 1 clients.Document row(s).", output)
        self.assertNotIn("json-rotation-secret", output)
        self.assertNotIn(before, output)
        self.assertNotIn(after, output)

    def test_unreadable_value_rolls_back_all_writes_without_leaking_data(self) -> None:
        valid_payload = {"secret": "rollback-valid-secret"}
        broken_payload = {"secret": "rollback-broken-secret"}
        damaged_token = "gAAAAAB-damaged-token-must-not-leak"

        with self._keyring(self.old_key):
            valid_document = self._create_document(valid_payload)
            broken_document = self._create_document(broken_payload)
            valid_before = self._raw_value(Document, "parsed_data", valid_document.pk)
            self._set_raw_value(Document, "parsed_data", broken_document.pk, damaged_token)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with self._keyring(self.new_key, self.old_key):
            with self.assertRaises(CommandError) as raised:
                call_command(
                    "rotate_fernet_fields",
                    "--model",
                    "clients.Document",
                    "--maintenance-confirmed",
                    stdout=stdout,
                    stderr=stderr,
                )
            valid_after = self._raw_value(Document, "parsed_data", valid_document.pk)
            broken_after = self._raw_value(Document, "parsed_data", broken_document.pk)

        self.assertEqual(valid_after, valid_before)
        self.assertEqual(broken_after, damaged_token)
        self.assertEqual(
            json.loads(Fernet(self.old_key).decrypt(valid_after.encode()).decode()),
            valid_payload,
        )
        with self.assertRaises(InvalidToken):
            Fernet(self.new_key).decrypt(valid_after.encode())

        output = stdout.getvalue() + stderr.getvalue() + str(raised.exception)
        self.assertIn("No changes were committed", output)
        for sensitive_value in (
            "rollback-valid-secret",
            "rollback-broken-secret",
            damaged_token,
            valid_before,
        ):
            self.assertNotIn(sensitive_value, output)

    def test_primary_key_only_distinguishes_fallback_tokens_then_passes_after_rotation(self) -> None:
        authority_number = "PRIMARY-KEY-ONLY-SECRET"
        with self._keyring(self.old_key):
            client = create_test_client()
            case = client.cases.get()
            case.authority_case_number = authority_number
            case.save(update_fields=["authority_case_number"])
            before = self._raw_value(Case, "authority_case_number", case.pk)

        with self._keyring(self.new_key, self.old_key):
            fallback_code, fallback_output = self._run_validator(
                "clients.Case",
                primary_key_only=False,
            )
            primary_code, primary_output = self._run_validator(
                "clients.Case",
                primary_key_only=True,
            )
            call_command(
                "rotate_fernet_fields",
                "--model",
                "clients.Case",
                "--maintenance-confirmed",
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )
            rotated_code, rotated_output = self._run_validator(
                "clients.Case",
                primary_key_only=True,
            )
            after = self._raw_value(Case, "authority_case_number", case.pk)

        self.assertEqual(fallback_code, 0)
        self.assertEqual(primary_code, 1)
        self.assertIn("DECRYPTION_FAILED", primary_output)
        self.assertEqual(rotated_code, 0)
        self.assertIn("All encrypted data is valid.", rotated_output)
        self.assertEqual(Fernet(self.new_key).decrypt(after.encode()).decode(), authority_number)
        with self.assertRaises(InvalidToken):
            Fernet(self.old_key).decrypt(after.encode())
        for output in (fallback_output, primary_output, rotated_output):
            self.assertNotIn(authority_number, output)
            self.assertNotIn(before, output)
            self.assertNotIn(after, output)

    def test_live_rotation_requires_explicit_maintenance_confirmation(self) -> None:
        with self._keyring(self.new_key, self.old_key):
            with self.assertRaisesMessage(CommandError, "--maintenance-confirmed"):
                call_command(
                    "rotate_fernet_fields",
                    "--model",
                    "clients.Document",
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                )

    def test_rotation_rejects_unknown_model_filter(self) -> None:
        with self._keyring(self.new_key, self.old_key):
            with self.assertRaisesMessage(CommandError, "No concrete model"):
                call_command(
                    "rotate_fernet_fields",
                    "--model",
                    "clients.DoesNotExist",
                    "--dry-run",
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                )

    def test_malformed_encrypted_json_aborts_without_normalizing_corruption(self) -> None:
        with self._keyring(self.old_key):
            document = self._create_document({"safe": "before"})
            malformed_token = Fernet(self.old_key).encrypt(b"not-json").decode()
            self._set_raw_value(Document, "parsed_data", document.pk, malformed_token)

        with self._keyring(self.new_key, self.old_key):
            with self.assertRaisesMessage(CommandError, "malformed encrypted JSON") as raised:
                call_command(
                    "rotate_fernet_fields",
                    "--model",
                    "clients.Document",
                    "--maintenance-confirmed",
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                )
            after = self._raw_value(Document, "parsed_data", document.pk)

        self.assertEqual(after, malformed_token)
        self.assertNotIn("not-json", str(raised.exception))
        self.assertNotIn(malformed_token, str(raised.exception))

    def test_rotation_bypasses_model_save_hooks(self) -> None:
        payload = {"safe": "hook-free"}
        with self._keyring(self.old_key):
            document = self._create_document(payload)

        with self._keyring(self.new_key, self.old_key):
            with patch.object(Document, "save", side_effect=AssertionError("save hook ran")):
                call_command(
                    "rotate_fernet_fields",
                    "--model",
                    "clients.Document",
                    "--maintenance-confirmed",
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                )
            after = self._raw_value(Document, "parsed_data", document.pk)

        self.assertEqual(json.loads(Fernet(self.new_key).decrypt(after.encode()).decode()), payload)

    def test_concurrent_field_update_aborts_and_rolls_back(self) -> None:
        with self._keyring(self.old_key):
            document = self._create_document({"safe": "concurrency"})
            before = self._raw_value(Document, "parsed_data", document.pk)

        target = (
            "legalize_site.management.commands.rotate_fernet_fields."
            "Command._conditional_update_raw"
        )
        with self._keyring(self.new_key, self.old_key):
            with patch(target, return_value=False):
                with self.assertRaisesMessage(CommandError, "concurrent update"):
                    call_command(
                        "rotate_fernet_fields",
                        "--model",
                        "clients.Document",
                        "--maintenance-confirmed",
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                    )
            after = self._raw_value(Document, "parsed_data", document.pk)

        self.assertEqual(after, before)

    def test_direct_save_rejects_reserved_unavailable_literal(self) -> None:
        with self._keyring(self.old_key):
            document = self._create_document({"safe": "before"})
            before = self._raw_value(Document, "parsed_data", document.pk)
            document.parsed_data = ENCRYPTED_VALUE_UNAVAILABLE  # type: ignore[assignment]
            with self.assertRaises(ValidationError):
                with transaction.atomic():
                    document.save(update_fields=["parsed_data"])
            after = self._raw_value(Document, "parsed_data", document.pk)

        self.assertEqual(after, before)

    def test_dry_run_reports_without_reencrypting(self) -> None:
        payload = {"secret": "dry-run-secret"}
        with self._keyring(self.old_key):
            document = self._create_document(payload)
            before = self._raw_value(Document, "parsed_data", document.pk)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with self._keyring(self.new_key, self.old_key):
            with patch.object(connection.features, "has_select_for_update", True):
                call_command(
                    "rotate_fernet_fields",
                    "--model",
                    "clients.Document",
                    "--dry-run",
                    stdout=stdout,
                    stderr=stderr,
                )
            after = self._raw_value(Document, "parsed_data", document.pk)
            primary_code, _primary_output = self._run_validator(
                "clients.Document",
                primary_key_only=True,
            )

        self.assertEqual(after, before)
        self.assertEqual(primary_code, 1)
        self.assertEqual(
            json.loads(Fernet(self.old_key).decrypt(after.encode()).decode()),
            payload,
        )
        with self.assertRaises(InvalidToken):
            Fernet(self.new_key).decrypt(after.encode())
        output = stdout.getvalue() + stderr.getvalue()
        self.assertIn("Would rotate 1 clients.Document row(s).", output)
        self.assertNotIn("dry-run-secret", output)
        self.assertNotIn(before, output)
