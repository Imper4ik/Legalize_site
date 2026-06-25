from __future__ import annotations

import logging
import sys
from typing import Any

from cryptography.fernet import InvalidToken
from django.apps import apps
from django.core.management.base import BaseCommand, CommandParser
from django.db import connection, models

from fernet_fields.fields import EncryptedFieldDecryptionError

logger = logging.getLogger(__name__)

# Status vocabulary required by the security spec. ``OK`` and skipped NULL/empty
# values are healthy; everything else is a failure that forces a non-zero exit.
STATUS_OK = "OK"
STATUS_NOT_ENCRYPTED = "NOT_ENCRYPTED"
STATUS_DECRYPTION_FAILED = "DECRYPTION_FAILED"
STATUS_ERROR = "ERROR"

FAILURE_STATUSES = {STATUS_NOT_ENCRYPTED, STATUS_DECRYPTION_FAILED, STATUS_ERROR}

DEFAULT_BATCH_SIZE = 500


class Command(BaseCommand):
    help = (
        "Validates Fernet-encrypted columns by streaming raw values in batches "
        "and attempting decryption. Plaintext (post-migration), decryption "
        "failures and unexpected errors all produce a non-zero exit code. "
        "Field values and exception payloads are never printed."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--model",
            dest="model",
            default=None,
            help="Limit validation to a single model: 'app_label.ModelName' or 'ModelName'.",
        )
        parser.add_argument(
            "--batch-size",
            dest="batch_size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            help=f"Number of rows to fetch per batch (default: {DEFAULT_BATCH_SIZE}).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        batch_size = options["batch_size"]
        if batch_size <= 0:
            self.stderr.write(self.style.ERROR("--batch-size must be a positive integer."))
            sys.exit(2)

        models_to_check = self._select_models(options.get("model"))
        if not models_to_check:
            self.stderr.write(self.style.ERROR("No matching model found for --model filter."))
            sys.exit(2)

        self.stdout.write(self.style.SUCCESS("Validating encrypted data..."))

        totals = {
            STATUS_OK: 0,
            STATUS_NOT_ENCRYPTED: 0,
            STATUS_DECRYPTION_FAILED: 0,
            STATUS_ERROR: 0,
        }
        total_checked = 0

        for model in models_to_check:
            encrypted_fields = self._encrypted_fields(model)
            if not encrypted_fields:
                continue

            table_name = model._meta.db_table
            pk = model._meta.pk
            if pk is None:
                continue
            pk_col = pk.column

            for field in encrypted_fields:
                self.stdout.write(
                    self.style.HTTP_INFO(
                        f"Checking {model.__name__}.{field.name} (table: {table_name})..."
                    )
                )
                fernet_obj = getattr(field, "_fernet", None)
                field_totals = self._check_field(
                    table_name=table_name,
                    pk_col=str(pk_col),
                    field_col=str(field.column),
                    fernet_obj=fernet_obj,
                    batch_size=batch_size,
                    model_name=model.__name__,
                    field_name=field.name,
                )
                for status, count in field_totals.items():
                    totals[status] += count
                    total_checked += count

        self._report(totals, total_checked)

        if any(totals[status] for status in FAILURE_STATUSES):
            sys.exit(1)

    def _select_models(self, model_filter: str | None) -> list[type[models.Model]]:
        all_models = list(apps.get_models())
        if not model_filter:
            return all_models

        wanted = model_filter.strip().lower()
        selected: list[type[models.Model]] = []
        for model in all_models:
            label = model._meta.label.lower()  # e.g. "clients.case"
            if wanted in (label, model.__name__.lower()):
                selected.append(model)
        return selected

    @staticmethod
    def _encrypted_fields(model: type[models.Model]) -> list[models.Field]:
        fields: list[models.Field] = []
        for field in model._meta.get_fields():
            if not isinstance(field, models.Field):
                continue
            class_name = field.__class__.__name__
            if "Encrypted" in class_name or hasattr(field, "_fernet"):
                fields.append(field)
        return fields

    def _check_field(
        self,
        *,
        table_name: str,
        pk_col: str,
        field_col: str,
        fernet_obj: Any,
        batch_size: int,
        model_name: str,
        field_name: str,
    ) -> dict[str, int]:
        field_totals = {
            STATUS_OK: 0,
            STATUS_NOT_ENCRYPTED: 0,
            STATUS_DECRYPTION_FAILED: 0,
            STATUS_ERROR: 0,
        }

        query = f'SELECT "{pk_col}", "{field_col}" FROM "{table_name}"'
        with connection.cursor() as cursor:
            try:
                cursor.execute(query)
            except Exception:
                # Never surface the raw exception text: it can echo row data.
                self.stderr.write(self.style.ERROR(f"Could not read table {table_name}."))
                field_totals[STATUS_ERROR] += 1
                return field_totals

            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                for pk, raw_val in rows:
                    status = self._classify_value(raw_val, fernet_obj)
                    if status is None:
                        continue  # NULL / empty values are allowed.
                    field_totals[status] += 1
                    line = f"{model_name} | ID: {pk} | Field: {field_name} | Status: {status}"
                    if status == STATUS_OK:
                        self.stdout.write(self.style.SUCCESS(line))
                    else:
                        self.stderr.write(self.style.ERROR(line))

        return field_totals

    @staticmethod
    def _classify_value(raw_val: Any, fernet_obj: Any) -> str | None:
        if raw_val is None or raw_val == "":
            return None  # Allowed: nothing to validate.

        is_token = isinstance(raw_val, str) and raw_val.startswith("gAAAA")
        if not is_token:
            # Plaintext after the encryption migration is a hard failure.
            return STATUS_NOT_ENCRYPTED

        if fernet_obj is None:
            return STATUS_ERROR

        try:
            # MultiFernet rotation is handled transparently by the field's keyring.
            fernet_obj.decrypt(raw_val.encode("utf-8"))
        except (InvalidToken, EncryptedFieldDecryptionError):
            return STATUS_DECRYPTION_FAILED
        except Exception:
            # Swallow the exception payload so no decrypted/raw data leaks.
            return STATUS_ERROR
        return STATUS_OK

    def _report(self, totals: dict[str, int], total_checked: int) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING("\n--- Validation summary ---"))
        self.stdout.write(f"Total values checked: {total_checked}")
        self.stdout.write(self.style.SUCCESS(f"{STATUS_OK}: {totals[STATUS_OK]}"))
        not_encrypted = totals[STATUS_NOT_ENCRYPTED]
        failed = totals[STATUS_DECRYPTION_FAILED]
        errored = totals[STATUS_ERROR]
        writer = self.style.ERROR if not_encrypted else self.style.WARNING
        self.stdout.write(writer(f"{STATUS_NOT_ENCRYPTED}: {not_encrypted}"))
        writer = self.style.ERROR if failed else self.style.WARNING
        self.stdout.write(writer(f"{STATUS_DECRYPTION_FAILED}: {failed}"))
        writer = self.style.ERROR if errored else self.style.WARNING
        self.stdout.write(writer(f"{STATUS_ERROR}: {errored}"))
        if any(totals[status] for status in FAILURE_STATUSES):
            self.stdout.write(self.style.ERROR("Encrypted data validation FAILED."))
        else:
            self.stdout.write(self.style.SUCCESS("All encrypted data is valid."))
