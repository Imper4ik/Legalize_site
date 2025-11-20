from datetime import date, timedelta
from decimal import Decimal

from django.test import SimpleTestCase

from clients.services.calculator import (
    MAX_MONTHS_LIVING,
    CalculatorResult,
    calculate_calculator_result,
)


class CalculatorServiceTests(SimpleTestCase):
    def setUp(self):
        self.base_data = {
            "total_end_date": date.today() + timedelta(days=30),
            "tuition_fee": Decimal("1000.00"),
            "tuition_currency": "PLN",
            "fee_type": "per_month",
            "months_in_period": 1,
            "rent_and_bills": Decimal("0"),
            "rent_currency": "PLN",
            "num_people": 1,
            "has_border": False,
        }

    def test_converts_eur_values_to_pln(self):
        data = {
            **self.base_data,
            "tuition_currency": "EUR",
            "tuition_fee": Decimal("10"),
            "rent_currency": "EUR",
            "rent_and_bills": Decimal("10"),
        }

        result = calculate_calculator_result(data, today=date.today())

        self.assertIsInstance(result, CalculatorResult)
        self.assertEqual(result.monthly_tuition_calculated, Decimal("43.00"))
        self.assertEqual(result.rent_total, Decimal("43.00"))

    def test_caps_months_to_maximum(self):
        far_future = date.today().replace(year=date.today().year + 3)
        data = {**self.base_data, "total_end_date": far_future}

        result = calculate_calculator_result(data, today=date.today())

        self.assertEqual(result.months_for_calc, MAX_MONTHS_LIVING)
        self.assertTrue(result.is_capped)

    def test_past_end_date_defaults_to_single_month(self):
        past_date = date.today() - timedelta(days=10)
        data = {**self.base_data, "total_end_date": past_date}

        result = calculate_calculator_result(data, today=date.today())

        self.assertEqual(result.total_months_real, 1)
        self.assertEqual(result.months_for_calc, 1)
