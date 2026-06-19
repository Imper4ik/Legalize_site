import os

from django.conf import settings
from django.test import SimpleTestCase, TestCase


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





class ReminderTranslationsTest(TestCase):
    def test_reminder_properties_dynamic_translations(self):
        from datetime import date

        from django.utils.translation import override

        from clients.constants import DocumentType
        from clients.models import Client, Document, Payment, Reminder

        client = Client.objects.create(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="+48111222333",
            citizenship="US",
            application_purpose="work"
        )

        doc = Document.objects.create(
            client=client,
            document_type=DocumentType.PASSPORT.value,
            expiry_date=date(2026, 12, 31)
        )

        payment = Payment.objects.create(
            client=client,
            service_description="consultation",
            total_amount=100.00,
            due_date=date(2026, 6, 15)
        )

        # Test document reminder
        doc_reminder = Reminder.objects.create(
            client=client,
            document=doc,
            due_date=date(2026, 12, 31),
            reminder_type="document",
            title="Document expires: Passport",
            notes="Document validity date for client John Doe: 31.12.2026."
        )

        # Test payment reminder. Creating a due payment automatically syncs its one-to-one reminder.
        payment_reminder = Reminder.objects.get(payment=payment)
        payment_reminder.title = "Payment due: Consultation"
        payment_reminder.notes = "Service total: 100.00; amount left to pay: 100.00; client: John Doe."
        payment_reminder.save(update_fields=["title", "notes"])

        # Test legal stay reminder
        mos_data = client.mos_application_data
        mos_data.legal_stay_until = date(2026, 7, 31)
        mos_data.save()
        client.refresh_from_db()

        stay_reminder = Reminder.objects.create(
            client=client,
            due_date=date(2026, 7, 30),
            reminder_type="legal_stay",
            title="Legal stay filing deadline: 30.07.2026",
            notes="Legal stay valid until: 31.07.2026. Recommended filing deadline considering weekends: 30.07.2026."
        )

        # English assertions
        with override("en"):
            self.assertEqual(doc_reminder.display_title, "Check document validity: Paszport")
            self.assertEqual(doc_reminder.display_notes, "Document validity date for client John Doe: 31.12.2026.")
            self.assertEqual(payment_reminder.display_title, "Payment due: Consultation")
            self.assertEqual(payment_reminder.display_notes, "Service total: 100.00; amount left to pay: 100.00; client: John Doe.")
            self.assertEqual(stay_reminder.display_title, "Legal stay filing deadline: 30.07.2026")
            self.assertEqual(stay_reminder.display_notes, "Legal stay valid until: 31.07.2026. Recommended filing deadline considering weekends: 30.07.2026.")

        # Polish assertions
        with override("pl"):
            self.assertEqual(doc_reminder.display_title, "Sprawdź ważność dokumentu: Paszport")
            self.assertEqual(doc_reminder.display_notes, "Data ważności dokumentu klienta John Doe: 31.12.2026.")
            self.assertEqual(payment_reminder.display_title, "Termin płatności: Konsultacja")
            self.assertEqual(payment_reminder.display_notes, "Kwota usługi: 100.00; pozostało do zapłaty: 100.00; klient: John Doe.")
            self.assertEqual(stay_reminder.display_title, "Termin złożenia w sprawie legalnego pobytu: 30.07.2026")
            self.assertEqual(stay_reminder.display_notes, "Legalny pobyt do: 31.07.2026. Zalecany termin złożenia z uwzględnieniem weekendów: 30.07.2026.")

        # Russian assertions
        with override("ru"):
            self.assertEqual(doc_reminder.display_title, "Проверьте срок действия документа: Паспорт")
            self.assertEqual(doc_reminder.display_notes, "Срок действия документа клиента John Doe: 31.12.2026.")
            self.assertEqual(payment_reminder.display_title, "Срок оплаты наступил: Консультация")
            self.assertEqual(payment_reminder.display_notes, "Сумма услуги: 100.00; осталось оплатить: 100.00; клиент: John Doe.")
            self.assertEqual(stay_reminder.display_title, "Срок подачи по легальному пребыванию: 30.07.2026")
            self.assertEqual(stay_reminder.display_notes, "Легальное пребывание до: 31.07.2026. Рекомендуемый срок подачи с учетом выходных: 30.07.2026.")


class NewTranslationsTest(TestCase):
    def test_new_translations_resolve(self):
        from django.utils.translation import gettext as _
        from django.utils.translation import override

        # Check 'for'
        with override("en"):
            self.assertEqual(_("for"), "for")
        with override("pl"):
            self.assertEqual(_("for"), "dla")
        with override("ru"):
            self.assertEqual(_("for"), "для")

        # Check workflow validation error
        msg = "Нельзя перейти к ожиданию решения без даты отпечатков."
        with override("en"):
            self.assertEqual(_(msg), "Cannot proceed to waiting for decision stage without a fingerprint date.")
        with override("pl"):
            self.assertEqual(_(msg), "Nie można przejść do etapu oczekiwania na decyzję bez daty odciski palców.")
        with override("ru"):
            self.assertEqual(_(msg), "Нельзя перейти к ожиданию решения без даты отпечатков.")

