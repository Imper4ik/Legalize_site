from __future__ import annotations

from datetime import date

from django.test import SimpleTestCase

from clients.services.zus_parser import _find_zus_period_month, _repair_ocr_digits


class RepairOcrDigitsTests(SimpleTestCase):
    def test_repairs_letter_digit_confusions_inside_numeric_tokens(self):
        self.assertEqual(_repair_ocr_digits("za miesiac o5 2o26"), "za miesiac 05 2026")
        self.assertEqual(_repair_ocr_digits("okres 2oi6"), "okres 2016")

    def test_leaves_ordinary_words_alone(self):
        text = "oslo obliczenia lista silos bob"
        self.assertEqual(_repair_ocr_digits(text), text)


class ZusPeriodMonthPhotoNoiseTests(SimpleTestCase):
    """Regressions for reporting-month detection on noisy photo OCR text."""

    def test_contextual_pattern_with_ocr_mangled_digits(self):
        text = "ZUS RCA imienny raport miesięczny za miesiąc O5.2O26 płatnik"
        self.assertEqual(_find_zus_period_month(text), date(2026, 5, 1))

    def test_fallback_requires_rca_marker_without_slot_context(self):
        # No "rca" in the text (photo OCR garbled it to "rga") and no context
        # keyword: without slot knowledge the parser must stay conservative.
        text = "ZUS RGA imienny raport 05.2026 ubezpieczony Jan Kowalski"
        self.assertIsNone(_find_zus_period_month(text))

    def test_fallback_enabled_by_slot_context(self):
        text = "ZUS RGA imienny raport 05.2026 ubezpieczony Jan Kowalski"
        self.assertEqual(
            _find_zus_period_month(text, assume_rca=True), date(2026, 5, 1)
        )

    def test_slot_context_does_not_match_full_print_dates(self):
        # Upload/print dates like 25.05.2026 must never be taken for the period.
        text = "wydrukowano 25.05.2026 podpis"
        self.assertIsNone(_find_zus_period_month(text, assume_rca=True))

    def test_identyfikator_line_with_noisy_digits(self):
        text = "Identyfikator raportu 01 O5 2O26 ZUS RCA"
        self.assertEqual(_find_zus_period_month(text), date(2026, 5, 1))
