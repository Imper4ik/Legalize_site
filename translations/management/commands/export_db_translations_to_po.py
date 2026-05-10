from __future__ import annotations

import polib
from django.core.management.base import BaseCommand
from translations.models import TranslationOverride
from translations.utils import get_po_files

class Command(BaseCommand):
    help = 'Export DB translation overrides to PO files'

    def add_arguments(self, parser):
        parser.add_argument('--no-compile', action='store_true', help='Disable compilemessages after export')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be done without changing files')

    def handle(self, *args, **options):
        po_files = get_po_files()
        no_compile = options['no_compile']
        dry_run = options['dry_run']

        overrides = TranslationOverride.objects.filter(is_active=True)
        
        if not overrides.exists():
            self.stdout.write(self.style.WARNING("No active DB overrides found to export."))
            return

        for lang, path in po_files.items():
            self.stdout.write(f"Updating {lang} PO file at {path}...")
            
            try:
                po = polib.pofile(path)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to read PO file {path}: {e}"))
                continue

            lang_overrides = overrides.filter(language=lang)
            updated_count = 0
            
            for override in lang_overrides:
                entry = po.find(override.msgid)
                if entry:
                    if entry.msgstr != override.text:
                        if dry_run:
                            self.stdout.write(f"[Dry-run] Would update '{override.msgid[:30]}' in {lang}")
                        else:
                            entry.msgstr = override.text
                            if 'fuzzy' in entry.flags:
                                entry.flags.remove('fuzzy')
                            updated_count += 1
                else:
                    if dry_run:
                        self.stdout.write(f"[Dry-run] Would add '{override.msgid[:30]}' to {lang}")
                    else:
                        new_entry = polib.POEntry(
                            msgid=override.msgid,
                            msgstr=override.text,
                            comment="Exported from DB TranslationOverride"
                        )
                        po.append(new_entry)
                        updated_count += 1
            
            if not dry_run and updated_count > 0:
                po.save()
                self.stdout.write(self.style.SUCCESS(f"Saved {updated_count} updates to {lang} PO file."))
            elif dry_run:
                self.stdout.write(f"[Dry-run] Would save updates to {lang} PO file.")

        if not no_compile and not dry_run:
            self.stdout.write("Compiling message catalogs...")
            try:
                from legalize_site.utils.i18n import compile_message_catalogs
                compile_message_catalogs()
                self.stdout.write(self.style.SUCCESS("Successfully compiled message catalogs."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to compile message catalogs: {e}"))
