from __future__ import annotations

import logging
import shutil
import struct
from pathlib import Path
from typing import Iterable

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError

logger = logging.getLogger(__name__)


def _iter_po_files(locale_dirs: Iterable[Path]) -> Iterable[Path]:
    seen: set[Path] = set()
    for base in locale_dirs:
        if not base:
            continue
        base = base.resolve()
        if base in seen or not base.exists():
            continue
        seen.add(base)
        yield from base.rglob("*.po")


def _write_mo_file(po_path: Path, mo_path: Path) -> None:
    """Compile a .po file to a .mo file using a pure-Python implementation.

    Adapted from Python's ``Tools/i18n/msgfmt.py`` so we do not depend on
    external gettext binaries.
    """

    messages = {}
    message_ctxt = None
    message_id = None
    message_strs: list[str] = []
    fuzzy = False

    def _add_message():
        if fuzzy or message_id is None:
            return
        # Support message context via \x04 separator (GNU gettext convention).
        key = message_id if message_ctxt is None else f"{message_ctxt}\x04{message_id}"
        messages[key] = message_strs

    with po_path.open("r", encoding="utf-8") as po_file:
        for raw_line in po_file:
            line = raw_line.strip()
            if line.startswith("#,") and "fuzzy" in line:
                fuzzy = True
                continue

            if line.startswith("msgctxt"):
                if message_id is not None:
                    _add_message()
                message_ctxt = eval(line[7:].strip())
                message_id = None
                message_strs = []
                fuzzy = False
                continue

            if line.startswith("msgid") and not line.startswith("msgid_plural"):
                if message_id is not None:
                    _add_message()
                message_ctxt = None if message_ctxt is None else message_ctxt
                message_id = eval(line[5:].strip())
                message_strs = []
                fuzzy = False
                continue

            if line.startswith("msgid_plural"):
                message_strs.append(eval(line[12:].strip()))
                continue

            if line.startswith("msgstr"):
                if line.startswith("msgstr["):
                    index = int(line[7: line.index("]")])
                    text = eval(line[line.index("]") + 1:].strip())
                    while len(message_strs) <= index:
                        message_strs.append("")
                    message_strs[index] = text
                else:
                    message_strs = [eval(line[6:].strip())]
                continue

            if line.startswith('"'):
                text = eval(line)
                if message_strs:
                    message_strs[-1] += text
                elif message_id is not None:
                    message_id += text
                elif message_ctxt is not None:
                    message_ctxt += text
                continue

        # Flush the last entry
        if message_id is not None:
            _add_message()

    ids = sorted(messages.keys())
    translated = ["\0".join(messages[msgid]) for msgid in ids]

    # Header: magic, version, #strings, orig_tab_offset, trans_tab_offset, hash size/off
    header_size = 7 * 4
    ids_table_offset = header_size
    strs_table_offset = ids_table_offset + len(ids) * 8

    # Compute offsets for originals
    orig_strings_offset = strs_table_offset + len(ids) * 8
    orig_offsets: list[tuple[int, int]] = []
    current = orig_strings_offset
    for msgid in ids:
        encoded = msgid.encode("utf-8")
        orig_offsets.append((len(encoded), current))
        current += len(encoded) + 1  # account for trailing NUL

    # Compute offsets for translations
    trans_offsets: list[tuple[int, int]] = []
    trans_strings_offset = current
    for msgstr in translated:
        encoded = msgstr.encode("utf-8")
        trans_offsets.append((len(encoded), trans_strings_offset))
        trans_strings_offset += len(encoded) + 1

    output = struct.pack(
        "Iiiiiii",
        0x950412de,  # magic
        0,  # version
        len(ids),  # number of strings
        ids_table_offset,
        strs_table_offset,
        0,
        0,
    )

    for length, offset in orig_offsets:
        output += struct.pack("ii", length, offset)

    for length, offset in trans_offsets:
        output += struct.pack("ii", length, offset)

    for msgid in ids:
        output += msgid.encode("utf-8") + b"\0"

    for msgstr in translated:
        output += msgstr.encode("utf-8") + b"\0"

    mo_path.parent.mkdir(parents=True, exist_ok=True)
    with mo_path.open("wb") as mo_file:
        mo_file.write(output)

    logger.info("Compiled %s -> %s using built-in msgfmt", po_path, mo_path)


def compile_message_catalogs() -> None:
    """Ensure .po files are compiled so translations are available.

    Tries Django's ``compilemessages`` (which uses ``msgfmt``) and falls back to
    a pure-Python compilation for environments where gettext binaries are
    unavailable.
    """

    locale_dirs = [
        Path(settings.BASE_DIR) / "locale",
        Path(__file__).resolve().parent.parent / "locale",
    ]

    msgfmt = shutil.which("msgfmt")
    if msgfmt:
        try:
            call_command("compilemessages", verbosity=0, ignore=["venv", ".venv"])
            return
        except (OSError, CommandError) as exc:
            logger.warning("compilemessages failed with msgfmt at %s: %s", msgfmt, exc)

    compiled_any = False
    for po_file in _iter_po_files(locale_dirs):
        try:
            mo_path = po_file.with_suffix(".mo")
            _write_mo_file(po_file, mo_path)
            compiled_any = True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Could not compile %s via Python msgfmt: %s", po_file, exc)

    if not compiled_any:
        logger.warning("No translation catalogs were compiled; translations may be unavailable")
