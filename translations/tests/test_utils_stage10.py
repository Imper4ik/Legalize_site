from __future__ import annotations

from unittest.mock import MagicMock, patch

import polib
from django.test import TestCase

from translations.utils import save_translation_entry


class TranslationUtilsStage10Tests(TestCase):
    @patch("translations.utils.get_po_files", return_value={"ru": "ru.po", "en": "en.po", "pl": "pl.po"})
    @patch("legalize_site.utils.i18n.compile_message_catalogs")
    def test_save_translation_entry_updates_entries_and_compiles(self, compile_mock, _files_mock):
        po_ru = polib.POFile()
        po_en = polib.POFile()
        po_pl = polib.POFile()
        po_ru.append(polib.POEntry(msgid="Калькулятор", msgstr="Калькулятор"))
        po_en.append(polib.POEntry(msgid="Калькулятор", msgstr="Calculator"))
        po_pl.append(polib.POEntry(msgid="Калькулятор", msgstr="Kalkulator"))

        po_map = {"ru.po": po_ru, "en.po": po_en, "pl.po": po_pl}

        def fake_pofile(path):
            po = po_map[path]
            po.save = MagicMock()
            return po

        with patch("translations.utils.polib.pofile", side_effect=fake_pofile):
            save_translation_entry("Калькулятор", ru="Кальк", en="Calc", pl="Kalk", storage="po")

        self.assertEqual(po_ru.find("Калькулятор").msgstr, "Кальк")
        self.assertEqual(po_en.find("Калькулятор").msgstr, "Calc")
        self.assertEqual(po_pl.find("Калькулятор").msgstr, "Kalk")
        compile_mock.assert_called_once()

    @patch("translations.utils.get_po_files", return_value={"ru": "ru.po"})
    @patch("legalize_site.utils.i18n.compile_message_catalogs")
    def test_save_translation_entry_logs_hash_without_raw_translation_text(self, _compile_mock, _files_mock):
        po_ru = polib.POFile()
        po_ru.append(polib.POEntry(msgid="Sensitive key", msgstr="old-secret-text"))

        def fake_pofile(path):
            po_ru.save = MagicMock()
            return po_ru

        with patch("translations.utils.polib.pofile", side_effect=fake_pofile):
            with self.assertLogs("translations.utils", level="INFO") as logs:
                save_translation_entry("Sensitive key", ru="new-secret-text", storage="po")

        log_text = "\n".join(logs.output)
        self.assertIn("msgid_hash=", log_text)
        self.assertNotIn("Sensitive key", log_text)
        self.assertNotIn("old-secret-text", log_text)
        self.assertNotIn("new-secret-text", log_text)

    @patch("translations.utils.get_po_files", return_value={"ru": "ru.po"})
    @patch("translations.utils.logger")
    def test_save_translation_entry_swallow_compile_errors(self, logger_mock, _files_mock):
        po_ru = polib.POFile()
        po_ru.append(polib.POEntry(msgid="Key", msgstr="Val"))

        def fake_pofile(path):
            po_ru.save = MagicMock()
            return po_ru

        with patch("translations.utils.polib.pofile", side_effect=fake_pofile):
            with patch("legalize_site.utils.i18n.compile_message_catalogs", side_effect=RuntimeError("boom")):
                save_translation_entry("Key", ru="New", storage="po")

        self.assertEqual(po_ru.find("Key").msgstr, "New")
        self.assertTrue(logger_mock.exception.called)
