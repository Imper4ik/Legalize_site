from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import InvalidToken
from django.apps import apps
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import connection, models, transaction
from django.utils.encoding import force_str

from fernet_fields import EncryptedJSONField, EncryptedTextField

ENCRYPTED_FIELD_TYPES = (EncryptedTextField, EncryptedJSONField)
ROTATION_BATCH_SIZE = 500


class Command(BaseCommand):
    help = "Re-encrypt project-local Fernet fields with the current primary FERNET_KEYS entry."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--model",
            action="append",
            default=[],
            help="Optional app_label.ModelName filter. Can be passed more than once.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report rows that would be rewritten without changing them.",
        )
        parser.add_argument(
            "--maintenance-confirmed",
            action="store_true",
            help=(
                "Confirm that all web and worker processes which can write the database "
                "have been drained or stopped for this rotation."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        model_filters = {str(item).strip().lower() for item in options.get("model", []) if str(item).strip()}
        dry_run = bool(options.get("dry_run", False))
        if not dry_run and not options.get("maintenance_confirmed", False):
            raise CommandError(
                "Refusing live key rotation. Drain or stop all database-writing web and worker "
                "processes, then pass --maintenance-confirmed."
            )

        selected_models = self._select_models(model_filters)
        model_updates: list[tuple[str, int]] = []

        # Keep the complete rotation in one transaction. Any unreadable value,
        # malformed JSON, or concurrent field update aborts every write.
        with transaction.atomic():
            for model, encrypted_fields in selected_models:
                updated_for_model = self._rotate_model(
                    model=model,
                    encrypted_fields=encrypted_fields,
                    dry_run=dry_run,
                )
                if updated_for_model:
                    model_updates.append((str(model._meta.label), updated_for_model))

        total_updated = sum(count for _label, count in model_updates)
        if total_updated == 0:
            self.stdout.write("No Fernet-encrypted values found to rotate.")
            return

        action = "Would rotate" if dry_run else "Rotated"
        for label, updated_for_model in model_updates:
            self.stdout.write(f"{action} {updated_for_model} {label} row(s).")

        suffix = " would be updated." if dry_run else " updated."
        self.stdout.write(self.style.SUCCESS(f"{total_updated} row(s){suffix}"))

    def _select_models(
        self,
        model_filters: set[str],
    ) -> list[tuple[type[models.Model], list[EncryptedTextField | EncryptedJSONField]]]:
        encrypted_models: list[
            tuple[type[models.Model], list[EncryptedTextField | EncryptedJSONField]]
        ] = []
        labels: set[str] = set()
        for model in apps.get_models():
            if model._meta.proxy:
                continue
            encrypted_fields = [
                field
                for field in model._meta.local_fields
                if isinstance(field, ENCRYPTED_FIELD_TYPES)
            ]
            if not encrypted_fields:
                continue
            label = str(model._meta.label).lower()
            labels.add(label)
            encrypted_models.append((model, encrypted_fields))

        unmatched = model_filters - labels
        if unmatched:
            requested = ", ".join(sorted(unmatched))
            raise CommandError(
                f"No concrete model with local Fernet fields matches --model: {requested}."
            )
        if model_filters:
            encrypted_models = [
                item for item in encrypted_models if str(item[0]._meta.label).lower() in model_filters
            ]
        if not encrypted_models:
            raise CommandError("No concrete models with Fernet-encrypted fields were found.")
        return encrypted_models

    def _rotate_model(
        self,
        *,
        model: type[models.Model],
        encrypted_fields: list[EncryptedTextField | EncryptedJSONField],
        dry_run: bool,
    ) -> int:
        label = str(model._meta.label)
        pk_field = model._meta.pk
        if pk_field is None:
            return 0

        quote = connection.ops.quote_name
        selected_columns = [str(pk_field.column), *(str(field.column) for field in encrypted_fields)]
        query = (
            f"SELECT {', '.join(quote(column) for column in selected_columns)} "
            f"FROM {quote(model._meta.db_table)} "
            f"ORDER BY {quote(str(pk_field.column))}"
        )
        if not dry_run and connection.features.has_select_for_update:
            query += " FOR UPDATE"

        updated_rows = 0
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                while True:
                    rows = cursor.fetchmany(ROTATION_BATCH_SIZE)
                    if not rows:
                        break
                    for row in rows:
                        pk, *raw_values = row
                        prepared_updates: list[
                            tuple[EncryptedTextField | EncryptedJSONField, Any, str]
                        ] = []
                        for field, raw_value in zip(encrypted_fields, raw_values, strict=True):
                            if raw_value in (None, ""):
                                continue
                            decoded = self._decode_raw_value(
                                field=field,
                                raw_value=raw_value,
                                label=label,
                                pk=pk,
                            )
                            try:
                                rotated_value = field.get_prep_value(decoded)
                            except Exception:
                                raise CommandError(
                                    f"Rotation aborted while preparing {label} (pk={pk}) "
                                    f"field '{field.name}'. No changes were committed."
                                ) from None
                            if not isinstance(rotated_value, str) or not rotated_value.startswith("gAAAA"):
                                raise CommandError(
                                    f"Rotation aborted while preparing {label} (pk={pk}) "
                                    f"field '{field.name}'. No changes were committed."
                                )
                            prepared_updates.append((field, raw_value, rotated_value))

                        if not prepared_updates:
                            continue
                        updated_rows += 1
                        if dry_run:
                            continue

                        for field, old_raw_value, rotated_value in prepared_updates:
                            if not self._conditional_update_raw(
                                model=model,
                                pk_field=pk_field,
                                pk=pk,
                                field=field,
                                old_raw_value=old_raw_value,
                                rotated_value=rotated_value,
                            ):
                                raise CommandError(
                                    f"Rotation aborted: concurrent update detected at {label} "
                                    f"(pk={pk}), field '{field.name}'. No changes were committed."
                                )
        except CommandError:
            raise
        except Exception:
            raise CommandError(
                f"Rotation aborted while accessing {label}. No changes were committed."
            ) from None
        return updated_rows

    @staticmethod
    def _decode_raw_value(
        *,
        field: EncryptedTextField | EncryptedJSONField,
        raw_value: Any,
        label: str,
        pk: Any,
    ) -> Any:
        raw_text = force_str(raw_value)
        if not raw_text.startswith("gAAAA"):
            raise CommandError(
                f"Rotation aborted: non-Fernet value at {label} (pk={pk}), "
                f"field '{field.name}'. No changes were committed."
            )
        try:
            plaintext = force_str(field._fernet.decrypt(raw_text.encode("utf-8")))
        except InvalidToken:
            raise CommandError(
                f"Rotation aborted: unreadable encrypted value at {label} (pk={pk}), "
                f"field '{field.name}'. No changes were committed."
            ) from None
        except Exception:
            raise CommandError(
                f"Rotation aborted while decrypting {label} (pk={pk}), "
                f"field '{field.name}'. No changes were committed."
            ) from None

        if isinstance(field, EncryptedJSONField):
            try:
                return json.loads(plaintext)
            except (TypeError, json.JSONDecodeError):
                raise CommandError(
                    f"Rotation aborted: malformed encrypted JSON at {label} (pk={pk}), "
                    f"field '{field.name}'. No changes were committed."
                ) from None
        return plaintext

    @staticmethod
    def _conditional_update_raw(
        *,
        model: type[models.Model],
        pk_field: models.Field[Any, Any],
        pk: Any,
        field: EncryptedTextField | EncryptedJSONField,
        old_raw_value: Any,
        rotated_value: str,
    ) -> bool:
        quote = connection.ops.quote_name
        query = (
            f"UPDATE {quote(model._meta.db_table)} "
            f"SET {quote(str(field.column))} = %s "
            f"WHERE {quote(str(pk_field.column))} = %s "
            f"AND {quote(str(field.column))} = %s"
        )
        with connection.cursor() as cursor:
            cursor.execute(query, [rotated_value, pk, old_raw_value])
            return cursor.rowcount == 1
