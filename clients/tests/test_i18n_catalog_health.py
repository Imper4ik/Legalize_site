"""CI guard for translation catalog health.

Fails when a catalog regresses into an untranslatable state: fuzzy entries,
empty required (EN/PL) translations, placeholder mismatches, or a catalog that
will not compile. RU is the source language, so an empty RU msgstr simply falls
back to the source and is allowed.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

LOCALE_ROOT = Path(settings.BASE_DIR) / "locale"
REQUIRED_TRANSLATED = ("en", "pl")
ALL_LANGS = ("en", "pl", "ru")


def _po_path(lang: str) -> Path:
    return LOCALE_ROOT / lang / "LC_MESSAGES" / "django.po"


def _iter_entries(text: str):
    """Yield (msgid, msgstr) for simple (non-plural) entries.

    Handles the PO multiline form where a value starts as `msgstr ""` and
    continues on following `"..."` lines, so an already-translated entry is not
    mistaken for an empty one.
    """
    lines = text.split("\n")
    i = 0
    n = len(lines)

    def read(idx: int, keyword: str):
        m = re.match(rf'{keyword} "(.*)"$', lines[idx])
        if not m:
            return None, idx
        value = m.group(1)
        idx += 1
        while idx < n:
            cont = re.match(r'"(.*)"$', lines[idx])
            if not cont:
                break
            value += cont.group(1)
            idx += 1
        return value, idx

    while i < n:
        if lines[i].startswith("msgid ") and not lines[i].startswith("msgid_plural"):
            msgid, j = read(i, "msgid")
            if j < n and lines[j].startswith("msgid_plural"):
                i = j + 1
                continue
            if j < n and lines[j].startswith("msgstr "):
                msgstr, k = read(j, "msgstr")
                yield msgid, msgstr
                i = k
                continue
        i += 1


class TranslationCatalogHealthTests(SimpleTestCase):
    def test_no_fuzzy_entries(self) -> None:
        offenders = {}
        for lang in ALL_LANGS:
            text = _po_path(lang).read_text(encoding="utf-8")
            count = text.count("#, fuzzy")
            if count:
                offenders[lang] = count
        self.assertEqual(offenders, {}, msg=f"Fuzzy translations present: {offenders}")

    def test_no_empty_required_translations(self) -> None:
        offenders: dict[str, list[str]] = {}
        for lang in REQUIRED_TRANSLATED:
            text = _po_path(lang).read_text(encoding="utf-8")
            empties = [
                msgid[:80]
                for msgid, msgstr in _iter_entries(text)
                if msgid != "" and msgstr == ""
            ]
            if empties:
                offenders[lang] = empties
        self.assertEqual(
            offenders,
            {},
            msg=f"Empty required translations (showing msgids): {offenders}",
        )

    def test_catalogs_compile_and_placeholders_match(self) -> None:
        msgfmt = shutil.which("msgfmt")
        if not msgfmt:
            self.skipTest("gettext msgfmt is not installed")
        for lang in ALL_LANGS:
            result = subprocess.run(
                [msgfmt, "--check-format", "-o", "/dev/null", str(_po_path(lang))],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                result.returncode,
                0,
                msg=f"{lang} catalog failed msgfmt --check-format:\n{result.stderr}",
            )
