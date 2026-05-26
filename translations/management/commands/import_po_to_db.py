from __future__ import annotations

import polib
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from translations.models import TranslationOverride
from translations.runtime import clear_translation_override_cache
from translations.utils import get_po_files


ALLOWED_OVERWRITE_SOURCES = {
    TranslationOverride.SOURCE_IMPORT,
    TranslationOverride.SOURCE_STUDIO,
    TranslationOverride.SOURCE_MANUAL,
}


def _parse_sources(raw_value: str) -> set[str]:
    if not raw_value:
        return set()

    sources = {item.strip() for item in raw_value.split(",") if item.strip()}
    invalid_sources = sources - ALLOWED_OVERWRITE_SOURCES
    if invalid_sources:
        allowed = ", ".join(sorted(ALLOWED_OVERWRITE_SOURCES))
        invalid = ", ".join(sorted(invalid_sources))
        raise CommandError(f"Invalid overwrite source(s): {invalid}. Allowed: {allowed}.")
    return sources


class Command(BaseCommand):
    help = "Import translations from PO files into the database"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--overwrite", action="store_true", help="Overwrite all existing DB overrides")
        parser.add_argument(
            "--overwrite-sources",
            default="",
            help=(
                "Comma-separated existing override sources to overwrite in addition to imported rows. "
                "Use this for one-time production repair, for example: studio,manual."
            ),
        )
        parser.add_argument("--dry-run", action="store_true", help="Show what would be done without changing the DB")
        parser.add_argument(
            "--fail-on-skipped",
            action="store_true",
            help="Exit non-zero if protected non-import overrides prevent syncing PO entries.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        po_files = get_po_files()
        overwrite = options["overwrite"]
        dry_run = options["dry_run"]
        fail_on_skipped = options["fail_on_skipped"]
        overwrite_sources = _parse_sources(options["overwrite_sources"])
        totals = {"created": 0, "updated": 0, "skipped": 0, "protected_skipped": 0}

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

                if (
                    existing is not None
                    and not overwrite
                    and existing.source != TranslationOverride.SOURCE_IMPORT
                    and existing.source not in overwrite_sources
                ):
                    totals["skipped"] += 1
                    totals["protected_skipped"] += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipping {existing.source} override for '{entry.msgid[:30]}' in {lang}"
                        )
                    )
                    continue

                if existing and existing.text == entry.msgstr and existing.is_active:
                    totals["skipped"] += 1
                    continue

                action = "update" if existing else "create"
                totals["updated" if existing else "created"] += 1
                if dry_run:
                    self.stdout.write(f"[Dry-run] Would {action} override for '{entry.msgid[:30]}' in {lang}")
                    continue

                _, created = TranslationOverride.objects.update_or_create(
                    msgid=entry.msgid,
                    language=lang,
                    defaults={
                        "text": entry.msgstr,
                        "is_active": True,
                        "source": TranslationOverride.SOURCE_IMPORT,
                    },
                )
                clear_translation_override_cache(entry.msgid, lang)
                message_action = "Created" if created else "Updated"
                self.stdout.write(self.style.SUCCESS(f"{message_action} override for '{entry.msgid[:30]}' in {lang}"))

        summary = (
            "Import finished: "
            f"created={totals['created']} updated={totals['updated']} skipped={totals['skipped']} "
            f"protected_skipped={totals['protected_skipped']}"
        )
        if fail_on_skipped and totals["protected_skipped"]:
            raise CommandError(summary)

        self.stdout.write(self.style.SUCCESS(summary))
