from __future__ import annotations

import os
from typing import Any

from django.core.management.base import BaseCommand

from clients.models import AppSettings

# Maps an environment variable to the AppSettings field it seeds. Only variables
# that are actually present in the environment are applied, so re-running with a
# partial env never clears already-configured fields.
ENV_FIELD_MAP: tuple[tuple[str, str], ...] = (
    ("TENANT_ORG_NAME", "organization_name"),
    ("TENANT_CONTACT_EMAIL", "contact_email"),
    ("TENANT_CONTACT_PHONE", "contact_phone"),
    ("TENANT_OFFICE_ADDRESS", "office_address"),
    ("TENANT_DEFAULT_PROXY", "default_proxy_name"),
    # RODO / data-controller identity (art. 13).
    ("TENANT_LEGAL_ENTITY_NAME", "legal_entity_name"),
    ("TENANT_NIP", "data_controller_nip"),
    ("TENANT_REGON", "data_controller_regon"),
    ("TENANT_KRS", "data_controller_krs"),
    ("TENANT_LEGAL_ADDRESS", "legal_address"),
    ("TENANT_REPRESENTATIVE", "representative_name"),
    ("TENANT_DPO_CONTACT", "dpo_contact"),
    ("TENANT_PRIVACY_POLICY_VERSION", "privacy_policy_version"),
    ("TENANT_DATA_RETENTION", "data_retention_summary"),
)


class Command(BaseCommand):
    help = (
        "Seed this instance's AppSettings (organization + RODO data-controller "
        "identity) from TENANT_* environment variables. Idempotent: only fields "
        "whose env var is set are applied. Intended for per-tenant deployments "
        "(one instance per firm)."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show which fields would change without writing to the database.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = options["dry_run"]
        settings = AppSettings.get_solo()

        changed: list[str] = []
        for env_var, field_name in ENV_FIELD_MAP:
            value = os.environ.get(env_var)
            if value is None:
                continue
            if getattr(settings, field_name) != value:
                changed.append(field_name)
                if not dry_run:
                    setattr(settings, field_name, value)

        if not changed:
            self.stdout.write(self.style.SUCCESS("Tenant settings already up to date."))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(f"[DRY RUN] Would update: {', '.join(changed)}"))
            return

        settings.save(update_fields=changed)
        self.stdout.write(self.style.SUCCESS(f"Updated tenant settings: {', '.join(changed)}"))
