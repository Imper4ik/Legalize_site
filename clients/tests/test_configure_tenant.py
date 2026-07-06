"""Per-tenant provisioning: seed AppSettings identity/RODO fields from env."""
from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from clients.models import AppSettings


class ConfigureTenantCommandTests(TestCase):
    def test_seeds_present_env_vars_only(self) -> None:
        env = {
            "TENANT_ORG_NAME": "Kancelaria XYZ",
            "TENANT_LEGAL_ENTITY_NAME": "Kancelaria XYZ Sp. z o.o.",
            "TENANT_NIP": "1234567890",
            "TENANT_PRIVACY_POLICY_VERSION": "2026-01",
        }
        with self.settings():  # keep test isolation explicit
            import os

            for key, value in env.items():
                os.environ[key] = value
            try:
                call_command("configure_tenant")
            finally:
                for key in env:
                    os.environ.pop(key, None)

        settings = AppSettings.get_solo()
        self.assertEqual(settings.organization_name, "Kancelaria XYZ")
        self.assertEqual(settings.legal_entity_name, "Kancelaria XYZ Sp. z o.o.")
        self.assertEqual(settings.data_controller_nip, "1234567890")
        self.assertEqual(settings.privacy_policy_version, "2026-01")
        # A field with no env var stays at its default (empty).
        self.assertEqual(settings.data_controller_regon, "")

    def test_dry_run_writes_nothing(self) -> None:
        import os

        os.environ["TENANT_ORG_NAME"] = "Dry Firm"
        out = StringIO()
        try:
            call_command("configure_tenant", "--dry-run", stdout=out)
        finally:
            os.environ.pop("TENANT_ORG_NAME", None)

        self.assertIn("Would update", out.getvalue())
        self.assertEqual(AppSettings.get_solo().organization_name, "")

    def test_is_idempotent(self) -> None:
        import os

        os.environ["TENANT_ORG_NAME"] = "Stable Firm"
        try:
            call_command("configure_tenant")
            out = StringIO()
            call_command("configure_tenant", stdout=out)
        finally:
            os.environ.pop("TENANT_ORG_NAME", None)

        self.assertIn("already up to date", out.getvalue())
        self.assertEqual(AppSettings.get_solo().organization_name, "Stable Firm")
