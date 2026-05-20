from __future__ import annotations

import polib
from django.core.management.base import BaseCommand

from translations.models import TranslationOverride
from translations.runtime import clear_translation_override_cache
from translations.utils import get_po_files


class Command(BaseCommand):
    help = "Import translations from PO files into the database"

    def add_arguments(self, parser):
        parser.add_argument("--overwrite", action="store_true", help="Overwrite all existing DB overrides")
        parser.add_argument("--dry-run", action="store_true", help="Show what would be done without changing the DB")

    def handle(self, *args, **options):
        po_files = get_po_files()
        overwrite = options["overwrite"]
        dry_run = options["dry_run"]
        totals = {"created": 0, "updated": 0, "skipped": 0}

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

                existing = TranslationOverride.objects.filter(msgid=entry.msgid, language=lang).first()

                if existing and not overwrite and existing.source != TranslationOverride.SOURCE_IMPORT:
                    totals["skipped"] += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipping non-import override for '{entry.msgid[:30]}' in {lang}"
                        )
                    )
                    continue

                if existing and existing.text == entry.msgstr and existing.is_active:
                    totals["skipped"] += 1
                    continue

                if dry_run:
                    action = "update" if existing else "create"
                    self.stdout.write(f"[Dry-run] Would {action} override for '{entry.msgid[:30]}' in {lang}")
                    continue

                override, created = TranslationOverride.objects.update_or_create(
                    msgid=entry.msgid,
                    language=lang,
                    defaults={
                        "text": entry.msgstr,
                        "is_active": True,
                        "source": TranslationOverride.SOURCE_IMPORT,
                    },
                )
                clear_translation_override_cache(entry.msgid, lang)
                action = "Created" if created else "Updated"
                totals["created" if created else "updated"] += 1
                self.stdout.write(self.style.SUCCESS(f"{action} override for '{entry.msgid[:30]}' in {lang}"))

        self.stdout.write(
            self.style.SUCCESS(
                "Import finished: "
                f"created={totals['created']} updated={totals['updated']} skipped={totals['skipped']}"
            )
        )