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
            content_normalized = content.replace('\r\n', '\n')

            for msgid, expected_msgstr in translations.items():
                msgid_marker = f'msgid "{msgid}"\n'
                idx = content_normalized.find(msgid_marker)
                self.assertNotEqual(idx, -1, f"Could not find msgid '{msgid}' in {lang}")

                # Find the msgstr line
                msgstr_marker = 'msgstr "'
                start_msgstr_line = content_normalized.find(msgstr_marker, idx + len(msgid_marker))
                self.assertNotEqual(start_msgstr_line, -1, f"Could not find msgstr for msgid '{msgid}' in {lang}")

                start_msgstr = start_msgstr_line + len(msgstr_marker)
                end_msgstr = content_normalized.find('"\n', start_msgstr)
                if end_msgstr == -1:
                    # If it's the last line in the file
                    end_msgstr = content_normalized.find('"', start_msgstr)

                actual_msgstr = content_normalized[start_msgstr:end_msgstr].replace('\n"', '')
                self.assertEqual(
                    actual_msgstr,
                    expected_msgstr,
                    f"msgstr for '{msgid}' in {lang} does not match expected."
                )

                # Check if it has fuzzy
                # Get the block immediately preceding our msgid
                preceding_text = content_normalized[max(0, idx - 500):idx]
                preceding_blocks = preceding_text.split('\n\n')
                comments_block = preceding_blocks[-1] if preceding_blocks else preceding_text
                self.assertNotIn('#, fuzzy', comments_block, f"msgid '{msgid}' in {lang} is still marked as fuzzy")
