from __future__ import annotations

from typing import Any

from django.apps import apps
from django.core.management.base import BaseCommand, CommandParser

from fernet_fields.fields import EncryptedTextField


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
            help="Report rows that would be rewritten without saving them.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        model_filters = {str(item).lower() for item in options.get("model", [])}
        dry_run = bool(options.get("dry_run", False))
        total_updated = 0

        for model in apps.get_models():
            label = str(model._meta.label)
            if model_filters and label.lower() not in model_filters:
                continue

            encrypted_fields = [
                field
                for field in model._meta.get_fields()
                if isinstance(field, EncryptedTextField)
            ]
            if not encrypted_fields:
                continue

            manager = getattr(model, "all_objects", model._default_manager)
            queryset = manager.all()
            updated_for_model = 0
            for obj in queryset.iterator():
                changed_fields = []
                for field in encrypted_fields:
                    try:
                        value = getattr(obj, field.attname)
                        if value in (None, ""):
                            continue
                        setattr(obj, field.attname, value)
                        changed_fields.append(field.attname)
                    except Exception as e:
                        self.stderr.write(
                            self.style.ERROR(
                                f"Failed to decrypt {label} (pk={obj.pk}) field '{field.name}': {e}"
                            )
                        )
                        continue

                if not changed_fields:
                    continue

                updated_for_model += 1
                if not dry_run:
                    obj.save(update_fields=changed_fields)

            if updated_for_model:
                total_updated += updated_for_model
                action = "Would rotate" if dry_run else "Rotated"
                self.stdout.write(f"{action} {updated_for_model} {label} row(s).")

        if total_updated == 0:
            self.stdout.write("No Fernet-encrypted values found to rotate.")
            return

        suffix = " would be updated." if dry_run else " updated."
        self.stdout.write(self.style.SUCCESS(f"{total_updated} row(s){suffix}"))
