from __future__ import annotations

import polib
from django.core.management.base import BaseCommand
from django.conf import settings
from translations.models import RuntimeTranslation
from translations.utils import get_po_files

class Command(BaseCommand):
    help = 'Import translations from PO files into the database'

    def add_arguments(self, parser):
        parser.add_argument('--overwrite', action='store_true', help='Overwrite existing DB overrides')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be done without changing the DB')

    def handle(self, *args, **options):
        po_files = get_po_files()
        overwrite = options['overwrite']
        dry_run = options['dry_run']

        for lang, path in po_files.items():
            self.stdout.write(f"Processing {lang} from {path}...")
            try:
                po = polib.pofile(path)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to read PO file {path}: {e}"))
                continue

            for entry in po:
                if not entry.msgid or not entry.msgstr:
                    continue
                
                exists = RuntimeTranslation.objects.filter(msgid=entry.msgid, language_code=lang).exists()
                
                if exists and not overwrite:
                    self.stdout.write(self.style.WARNING(f"Skipping existing override for '{entry.msgid[:30]}' in {lang}"))
                    continue
                
                if dry_run:
                    self.stdout.write(f"[Dry-run] Would save override for '{entry.msgid[:30]}' in {lang}")
                else:
                    override, created = RuntimeTranslation.objects.update_or_create(
                        msgid=entry.msgid,
                        language_code=lang,
                        defaults={
                            'msgstr': entry.msgstr,
                            'is_active': True,
                            'source': 'po_import'
                        }
                    )
                    action = "Created" if created else "Updated"
                    self.stdout.write(self.style.SUCCESS(f"{action} override for '{entry.msgid[:30]}' in {lang}"))
