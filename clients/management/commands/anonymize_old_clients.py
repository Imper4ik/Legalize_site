import logging
from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from clients.models import Client

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Anonymize clients older than 5 years to comply with GDPR (Right to be Forgotten)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            '--years',
            type=int,
            default=5,
            help='Number of years to consider a client "old" and subject to anonymization (default: 5)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run the command without making any actual changes to the database.',
        )
        parser.add_argument(
            '--execute',
            action='store_true',
            help='Actually anonymize eligible clients. Requires --confirm.',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Required together with --execute to confirm the destructive operation.',
        )

    def handle(self, *args: Any, **options: Any) -> None:
        years = options['years']
        dry_run = bool(options['dry_run'])
        execute = bool(options['execute'])
        confirm = bool(options['confirm'])

        if dry_run and execute:
            raise CommandError('--dry-run cannot be combined with --execute.')
        if execute and not confirm:
            raise CommandError('Refusing to anonymize without --confirm.')

        cutoff_date = timezone.now().date() - timedelta(days=years * 365)

        # We consider a client 'old' if their legal_basis_end_date is before the cutoff date,
        # or if legal_basis_end_date is None, their created_at date.
        # But for simplicity, we will query based on created_at for absolute age,
        # and ensure legal_basis_end_date (if exists) is also past the cutoff.

        # Use all_objects: archived (soft-deleted) clients are exactly the ones
        # most likely to be past retention, and the default manager would skip
        # them, silently leaving their PII in place. Already-anonymized rows are
        # excluded so the run is idempotent.
        clients_to_anonymize = Client.all_objects.filter(
            created_at__date__lte=cutoff_date
        ).exclude(
            legal_basis_end_date__gte=cutoff_date
        ).exclude(
            first_name__startswith='Anonymized'
        ).exclude(
            # A legal hold blocks age-based erasure too (active case, accounting,
            # or the firm's legal-defence needs).
            legal_hold=True
        )

        count = clients_to_anonymize.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS('No old clients found to anonymize.'))
            return

        self.stdout.write(self.style.WARNING(f'Found {count} clients older than {years} years.'))

        if dry_run or not execute:
            heading = '[DRY RUN] Would have anonymized the following:' if dry_run else 'Report only. Eligible client IDs:'
            self.stdout.write(self.style.SUCCESS(heading))
            for client in clients_to_anonymize:
                # Do not print PII (names) to the console (GDPR / spec §13).
                self.stdout.write(f' - ID {client.id}')
            self.stdout.write(
                self.style.SUCCESS(
                    'No data was changed. Re-run with --execute --confirm to anonymize eligible records.'
                )
            )
            return

        from clients.services.anonymization import anonymize_client

        anonymized_count = 0
        for client in clients_to_anonymize:
            # Per-client transaction lives in the service (spec §9): process state
            # is anonymized at the case level; the removed Client.case_number is
            # never touched.
            anonymize_client(client)
            anonymized_count += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully anonymized {anonymized_count} clients.'))
