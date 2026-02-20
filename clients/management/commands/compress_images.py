"""Django management command to compress existing document images."""
from django.core.management.base import BaseCommand
from pathlib import Path

from clients.models import Document
from clients.services.image_compression import compress_existing_file, should_compress


class Command(BaseCommand):
    help = 'Compress existing document images to save storage space'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be compressed without actually doing it',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of documents to process',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']

        # Find all documents with image files
        documents = Document.objects.exclude(file='').exclude(file__isnull=True)
        
        if limit:
            documents = documents[:limit]

        total = documents.count()
        self.stdout.write(f"Found {total} documents to check")

        compressed_count = 0
        skipped_count = 0
        error_count = 0
        total_saved_bytes = 0

        for i, doc in enumerate(documents, 1):
            if not doc.file:
                continue

            file_path = Path(doc.file.path)
            
            # Check if file exists and should be compressed
            if not file_path.exists():
                self.stdout.write(
                    self.style.WARNING(f"[{i}/{total}] File not found: {file_path}")
                )
                error_count += 1
                continue

            if not should_compress(file_path):
                skipped_count += 1
                continue

            original_size = file_path.stat().st_size

            self.stdout.write(
                f"[{i}/{total}] Processing: {doc.client.last_name} - {doc.document_type}"
            )

            if dry_run:
                self.stdout.write(
                    self.style.WARNING(f"  Would compress: {file_path.name} ({original_size / 1024:.1f}KB)")
                )
                compressed_count += 1
                continue

            # Compress the file
            try:
                success = compress_existing_file(file_path)
                if success:
                    new_path = file_path.with_suffix('.webp') if file_path.suffix.lower() != '.webp' else file_path
                    if new_path.exists():
                        new_size = new_path.stat().st_size
                        saved = original_size - new_size
                        total_saved_bytes += saved
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  Compressed: {original_size / 1024:.1f}KB → {new_size / 1024:.1f}KB "
                                f"(saved {saved / 1024:.1f}KB, {(saved / original_size) * 100:.1f}%)"
                            )
                        )
                        compressed_count += 1
                        
                        # Update file path in database if extension changed
                        if new_path != file_path:
                            doc.file.name = str(new_path.relative_to(Path(doc.file.storage.location)))
                            doc.save(update_fields=['file'])
                else:
                    self.stdout.write(self.style.ERROR("  Failed to compress"))
                    error_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Error: {e}"))
                error_count += 1

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("COMPRESSION SUMMARY"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"Total documents checked: {total}")
        self.stdout.write(f"Compressed: {compressed_count}")
        self.stdout.write(f"Skipped (non-image): {skipped_count}")
        self.stdout.write(f"Errors: {error_count}")
        
        if not dry_run and total_saved_bytes > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nTotal space saved: {total_saved_bytes / 1024 / 1024:.2f} MB"
                )
            )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING("\nDRY RUN - No files were actually compressed")
            )
            self.stdout.write("Run without --dry-run to compress files")
