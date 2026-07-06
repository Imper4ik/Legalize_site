import logging
from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
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

    def handle(self, *args: Any, **options: Any) -> None:
        years = options['years']
        dry_run = options['dry_run']

        cutoff_date = timezone.now().date() - timedelta(days=years * 365)

        # We consider a client 'old' if their legal_basis_end_date is before the cutoff date,
        # or if legal_basis_end_date is None, their created_at date.
        # But for simplicity, we will query based on created_at for absolute age,
        # and ensure legal_basis_end_date (if exists) is also past the cutoff.

        clients_to_anonymize = Client.objects.filter(
            created_at__date__lte=cutoff_date
        ).exclude(
            legal_basis_end_date__gte=cutoff_date
        ).exclude(
            first_name__startswith='Anonymized'
        )

        count = clients_to_anonymize.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS('No old clients found to anonymize.'))
            return

        self.stdout.write(self.style.WARNING(f'Found {count} clients older than {years} years.'))

        if dry_run:
            self.stdout.write(self.style.SUCCESS('[DRY RUN] Would have anonymized the following:'))
            for client in clients_to_anonymize:
                # Do not print PII (names) to the console (GDPR / spec §13).
                self.stdout.write(f' - ID {client.id}')
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
