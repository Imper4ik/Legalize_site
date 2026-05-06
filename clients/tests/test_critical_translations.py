import os
import re
from django.test import SimpleTestCase
from django.conf import settings

class CriticalTranslationsTest(SimpleTestCase):
    def test_critical_translations_not_fuzzy_and_correct(self):
        critical_map = {
            'pl': {
                "Тема письма": "Temat wiadomości",
                "Компания / Работодатель": "Firma / Pracodawca",
                "Срок оплаты": "Termin płatności",
                "Отправить": "Wyślij",
                "История email": "Historia wiadomości e-mail",
                "Нет напоминаний по оплатам, соответствующих фильтрам.": "Brak przypomnień o płatnościach pasujących do filtrów.",
                "Вы уверены, что хотите безвозвратно удалить это напоминание?": "Czy na pewno chcesz trwale usunąć to przypomnienie?"
            },
            'en': {
                "Тема письма": "Email subject",
                "Компания / Работодатель": "Company / Employer",
                "Срок оплаты": "Payment due date",
                "Отправить": "Send",
                "История email": "Email history",
                "Нет напоминаний по оплатам, соответствующих фильтрам.": "No payment reminders match the filters.",
                "Вы уверены, что хотите безвозвратно удалить это напоминание?": "Are you sure you want to permanently delete this reminder?"
            },
            'ru': {
                "Тема письма": "Тема письма",
                "Компания / Работодатель": "Компания / Работодатель",
                "Срок оплаты": "Срок оплаты",
                "Отправить": "Отправить",
                "История email": "История email",
                "Нет напоминаний по оплатам, соответствующих фильтрам.": "Нет напоминаний по оплатам, соответствующих фильтрам.",
                "Вы уверены, что хотите безвозвратно удалить это напоминание?": "Вы уверены, что хотите безвозвратно удалить это напоминание?"
            }
        }

        base_dir = settings.BASE_DIR
        locale_dir = os.path.join(base_dir, 'locale')

        for lang, translations in critical_map.items():
            po_path = os.path.join(locale_dir, lang, 'LC_MESSAGES', 'django.po')
            self.assertTrue(os.path.exists(po_path), f"PO file for {lang} does not exist at {po_path}")

            with open(po_path, 'r', encoding='utf-8') as f:
                content = f.read()

            for msgid, expected_msgstr in translations.items():
                # Find block for this msgid
                # Match everything from `msgid "..."` to `msgstr "..."` (and possibly multi-line msgstr)
                # But to just check fuzzy, we look at the lines right before msgid

                # regex to find the msgstr for the given msgid
                msgid_escaped = re.escape(msgid)
                pattern_msgstr = re.compile(rf'msgid "{msgid_escaped}"\nmsgstr "(.*?)"', re.DOTALL)
                match = pattern_msgstr.search(content)
                self.assertIsNotNone(match, f"Could not find msgid '{msgid}' in {lang}")

                actual_msgstr = match.group(1).replace('\n"', '')
                self.assertEqual(
                    actual_msgstr,
                    expected_msgstr,
                    f"msgstr for '{msgid}' in {lang} does not match expected."
                )

                # Check if it has fuzzy
                # Find the block up to msgid
                pattern_block = re.compile(rf'(?:^|\n)(.*?)\nmsgid "{msgid_escaped}"', re.DOTALL)
                block_matches = pattern_block.findall(content)

                # The last match is the block immediately preceding our msgid
                if block_matches:
                    preceding_block = block_matches[-1]
                    # Only look at the preceding comments block
                    comments_block = preceding_block.split('\n\n')[-1]
                    self.assertNotIn('#, fuzzy', comments_block, f"msgid '{msgid}' in {lang} is still marked as fuzzy")
