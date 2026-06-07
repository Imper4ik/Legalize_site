import logging
from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

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
                self.stdout.write(f' - ID {client.id}: {client.first_name} {client.last_name}')
            return

        anonymized_count = 0
        with transaction.atomic():
            for client in clients_to_anonymize:
                client_id = client.id
                
                # Anonymize PII
                client.first_name = f'Anonymized_{client_id}'
                client.last_name = 'User'
                client.email = f'deleted_{client_id}@example.com'
                client.phone = '000000000'
                client.case_number = f'DELETED-{client_id}'
                client.company = None
                
                # We do not delete financial records to keep aggregate statistics intact,
                # but we should delete any uploaded documents.
                documents = client.documents.all()
                docs_deleted = 0
                for doc in documents:
                    if doc.file:
                        doc.file.delete(save=False) # Physical file deletion
                    doc.delete(hard=True) # Database record deletion
                    docs_deleted += 1

                client.save()
                anonymized_count += 1
                logger.info("Anonymized client ID %s and deleted %s documents (GDPR).", client_id, docs_deleted)

        self.stdout.write(self.style.SUCCESS(f'Successfully anonymized {anonymized_count} clients.'))
