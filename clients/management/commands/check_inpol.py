from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError

from clients.services.inpol import (
    InpolClient,
    InpolCredentials,
    InpolStatusRepository,
    check_inpol_and_update_clients,
)
from clients.models import InpolAccount


class Command(BaseCommand):
    help = "Fetch inPOL proceedings via the API, detect status changes, and sync them to client records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            help="Login email for inPOL (defaults to INPOL_EMAIL environment variable).",
        )
        parser.add_argument(
            "--password",
            help="Login password for inPOL (defaults to INPOL_PASSWORD environment variable).",
        )
        parser.add_argument(
            "--base-url",
            help="Base URL for the inPOL portal (defaults to INPOL_BASE_URL environment variable).",
        )

    def handle(self, *args, **options):
        email = options.get("email") or os.environ.get("INPOL_EMAIL")
        password = options.get("password") or os.environ.get("INPOL_PASSWORD")
        base_url = options.get("base_url") or os.environ.get("INPOL_BASE_URL")

        if not (email and password and base_url):
            account = self._get_active_account()
            if account:
                email = email or account.email
                password = password or account.password
                base_url = base_url or account.base_url

        if not email or not password or not base_url:
            raise CommandError(
                "Missing inPOL credentials. Provide --email/--password/--base-url, "
                "set INPOL_EMAIL/INPOL_PASSWORD/INPOL_BASE_URL, or create an "
                "active inPOL account in the admin panel."
            )

        credentials = InpolCredentials(email=email, password=password)
        client = InpolClient(base_url)
        repository = InpolStatusRepository()

        self.stdout.write("Checking inPOL for updates...")
        changes = check_inpol_and_update_clients(credentials, client, repository)

        if not changes:
            self.stdout.write(self.style.SUCCESS("No changes detected."))
            return

        for change in changes:
            proceeding = change.proceeding
            previous_status = change.previous_status or "(new)"
            current_status = proceeding.status or "(empty)"
            self.stdout.write(
                f"{proceeding.case_number or proceeding.proceeding_id}: "
                f"{previous_status} -> {current_status}"
            )

        self.stdout.write(self.style.SUCCESS(f"Applied {len(changes)} change(s) to client records."))

    def _get_active_account(self) -> InpolAccount | None:
        return (
            InpolAccount.objects.filter(is_active=True)
            .order_by("-updated_at", "-id")
            .first()
        )
