from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from clients.services.inpol import InpolClient, InpolStatusRepository, check_inpol_and_update_clients
from clients.services.inpol_credentials import resolve_inpol_config


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
        parser.add_argument(
            "--silent",
            action="store_true",
            help="Suppress normal output (useful for background polling).",
        )

    def handle(self, *args, **options):
        try:
            config = resolve_inpol_config(
                email=options.get("email"),
                password=options.get("password"),
                base_url=options.get("base_url"),
            )
        except Exception as exc:
            raise CommandError(str(exc))

        credentials = config.credentials
        client = InpolClient(config.base_url)
        repository = InpolStatusRepository()

        if not options.get("silent"):
            self.stdout.write("Checking inPOL for updates...")

        changes = check_inpol_and_update_clients(credentials, client, repository)

        if not options.get("silent"):
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
