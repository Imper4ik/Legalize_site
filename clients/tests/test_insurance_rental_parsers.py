from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.test import SimpleTestCase

from clients.services.insurance_parser import _find_coverage, parse_insurance_doc
from clients.services.rental_parser import _find_address, _find_rental_cost, parse_rental_doc


class InsuranceCoverageExtractionTests(SimpleTestCase):
    def test_keyworded_eur_coverage(self):
        amount, currency = _find_coverage("Suma ubezpieczenia: 30 000 EUR na osobę")
        self.assertEqual((amount, currency), (30000.0, "EUR"))

    def test_zloty_alias_normalized_to_pln(self):
        amount, currency = _find_coverage("suma gwarancyjna 150 000 zł")
        self.assertEqual((amount, currency), (150000.0, "PLN"))

    def test_low_amounts_are_not_coverage(self):
        # Premiums / fees (e.g. "składka 250 zł") must not be taken for coverage.
        amount, currency = _find_coverage("składka miesięczna 250 zł")
        self.assertIsNone(amount)
        self.assertIsNone(currency)

    def test_bare_amount_fallback(self):
        amount, currency = _find_coverage("ochrona do wysokości 120 000 PLN rocznie")
        self.assertEqual((amount, currency), (120000.0, "PLN"))


class InsuranceDocParseTests(SimpleTestCase):
    def _parse(self, text: str):
        with patch("clients.services.insurance_parser.extract_text", return_value=text):
            return parse_insurance_doc("dummy.pdf")

    def test_full_policy_extraction(self):
        parsed = self._parse(
            "POLISA UBEZPIECZENIOWA\n"
            "Ubezpieczony: Jan Kowalski\n"
            "Suma ubezpieczenia: 30 000 EUR\n"
            "Okres ubezpieczenia do 31.12.2026\n"
        )
        self.assertIsNone(parsed.error)
        self.assertEqual(parsed.coverage_amount, 30000.0)
        self.assertEqual(parsed.currency, "EUR")
        self.assertEqual(parsed.valid_until, date(2026, 12, 31))

    def test_empty_ocr_text_reports_no_text(self):
        parsed = self._parse("")
        self.assertEqual(parsed.error, "no_text")


class RentalCostExtractionTests(SimpleTestCase):
    def test_keyworded_czynsz(self):
        self.assertEqual(_find_rental_cost("Czynsz najmu wynosi 2 500 zł miesięcznie"), 2500.0)

    def test_out_of_range_amounts_rejected(self):
        # A property deposit or price (250 000) is not a monthly rent.
        self.assertIsNone(_find_rental_cost("wartość nieruchomości 250 000 PLN"))

    def test_amount_with_decimal_comma(self):
        self.assertEqual(_find_rental_cost("opłata 1 850,50 za miesiąc"), 1850.5)


class RentalAddressExtractionTests(SimpleTestCase):
    def test_postcode_address(self):
        found = _find_address("lokal przy ul. Marszałkowska 10/12 m. 5, 00-590 Warszawa, zwany dalej")
        self.assertIsNotNone(found)
        self.assertIn("00-590", found)

    def test_street_fallback_without_postcode(self):
        found = _find_address("przedmiotem najmu jest lokal przy ul. Polna 7")
        self.assertIsNotNone(found)
        self.assertIn("Polna", found)

    def test_no_address(self):
        self.assertIsNone(_find_address("umowa zawarta pomiędzy stronami"))


class RentalDocParseTests(SimpleTestCase):
    def _parse(self, text: str):
        with patch("clients.services.rental_parser.extract_text", return_value=text):
            return parse_rental_doc("dummy.pdf")

    def test_full_agreement_extraction(self):
        parsed = self._parse(
            "UMOWA NAJMU LOKALU\n"
            "Najemca: Anna Nowak\n"
            "lokal przy ul. Marszałkowska 10/12 m. 5, 00-590 Warszawa\n"
            "Czynsz najmu: 2 800 zł miesięcznie\n"
            "Umowa obowiązuje do 30.06.2027\n"
        )
        self.assertIsNone(parsed.error)
        self.assertIn("00-590", parsed.address or "")
        self.assertEqual(parsed.monthly_cost, 2800.0)
        self.assertEqual(parsed.valid_until, date(2027, 6, 30))

    def test_empty_ocr_text_reports_no_text(self):
        parsed = self._parse("")
        self.assertEqual(parsed.error, "no_text")
