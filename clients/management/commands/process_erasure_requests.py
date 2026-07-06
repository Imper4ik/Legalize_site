from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from clients.models import Client


class Command(BaseCommand):
    help = (
        "Fulfil pending RODO art. 17 erasure requests by anonymizing clients "
        "who requested deletion (Client.erasure_requested_at set, not yet fulfilled)."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List clients that would be anonymized without changing the database.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = options["dry_run"]

        pending = Client.all_objects.filter(
            erasure_requested_at__isnull=False,
            erasure_fulfilled_at__isnull=True,
        )
        count = pending.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS("No pending erasure requests."))
            return

        self.stdout.write(self.style.WARNING(f"Found {count} pending erasure request(s)."))

        if dry_run:
            self.stdout.write(self.style.SUCCESS("[DRY RUN] Would anonymize:"))
            for client in pending:
                # Never print PII to the console.
                self.stdout.write(f" - ID {client.id}")
            return

        from clients.services.anonymization import anonymize_client

        fulfilled = 0
        for client in pending:
            anonymize_client(client, mark_erasure_fulfilled=True)
            fulfilled += 1

        self.stdout.write(self.style.SUCCESS(f"Fulfilled {fulfilled} erasure request(s)."))
