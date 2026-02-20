"""Domain logic for the bank statement calculator."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Optional

import requests
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


LIVING_ALLOWANCE = Decimal("1010")
TICKET_BORDER = Decimal("500")
TICKET_NO_BORDER = Decimal("2500")
MAX_MONTHS_LIVING = 15
DEFAULT_EUR_TO_PLN_RATE = Decimal("4.3")
CURRENCY_PLN = "PLN"
CURRENCY_EUR = "EUR"


@dataclass
class CalculatorResult:
    rent_total: Decimal
    num_people: int
    rent_per_person: Decimal
    tuition_total: Decimal
    months_in_period: int
    monthly_tuition_calculated: Decimal
    total_monthly_costs: Decimal
    total_months_real: int
    months_for_calc: int
    is_capped: bool
    total_base_cost: Decimal
    return_ticket: Decimal
    final_total_required: Decimal


def get_eur_to_pln_rate() -> Decimal:
    """Fetch current EUR to PLN exchange rate from NBP API with caching."""
    cache_key = "eur_to_pln_rate"
    cached_rate = cache.get(cache_key)
    
    if cached_rate is not None:
        return cached_rate

    try:
        # NBP API does not require an API key
        response = requests.get("http://api.nbp.pl/api/exchangerates/rates/a/eur/?format=json", timeout=5)
        response.raise_for_status()
        data = response.json()
        rate = Decimal(str(data["rates"][0]["mid"]))
        
        # Cache for 12 hours
        cache.set(cache_key, rate, timeout=12 * 60 * 60)
        return rate
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch EUR/PLN rate from NBP API: {e}. Using default.")
        return DEFAULT_EUR_TO_PLN_RATE
    except (KeyError, IndexError, ValueError) as e:
        logger.warning(f"Failed to parse EUR/PLN rate from NBP API: {e}. Using default.")
        return DEFAULT_EUR_TO_PLN_RATE


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def convert_to_pln(amount: Decimal, currency: str) -> Decimal:
    """Convert given amount to PLN using the current EUR to PLN rate."""
    if currency == CURRENCY_EUR:
        current_rate = get_eur_to_pln_rate()
        return _quantize_money(amount * current_rate)
    return _quantize_money(amount)


def calculate_calculator_result(data: dict, *, today: Optional[date] = None) -> CalculatorResult:
    """Perform calculator computations based on validated input data."""

    tuition_fee = Decimal(data["tuition_fee"])
    tuition_currency = data["tuition_currency"]
    rent_and_bills = Decimal(data["rent_and_bills"])
    rent_currency = data["rent_currency"]
    months_in_period = max(int(data["months_in_period"]), 1)
    num_people = max(int(data["num_people"]), 1)
    has_border = bool(data.get("has_border"))
    fee_type = data.get("fee_type", "per_month")

    tuition_fee_pln = convert_to_pln(tuition_fee, tuition_currency)
    if fee_type != "per_month":
        monthly_tuition = _quantize_money(tuition_fee_pln / months_in_period)
    else:
        monthly_tuition = tuition_fee_pln
    tuition_total = _quantize_money(monthly_tuition * months_in_period)

    monthly_rent_and_bills = convert_to_pln(rent_and_bills, rent_currency)
    rent_per_person = _quantize_money(monthly_rent_and_bills / num_people)

    total_end_date: date = data["total_end_date"]
    current_date = today or timezone.now().date()

    if total_end_date < current_date:
        total_months_real = 1
    else:
        year_diff = total_end_date.year - current_date.year
        month_diff = total_end_date.month - current_date.month
        total_months_real = year_diff * 12 + month_diff + 1

    total_months_real = max(total_months_real, 1)

    months_for_calc = min(total_months_real, MAX_MONTHS_LIVING)
    is_capped = total_months_real > MAX_MONTHS_LIVING

    return_ticket = TICKET_BORDER if has_border else TICKET_NO_BORDER

    total_monthly_costs = _quantize_money(rent_per_person + monthly_tuition + LIVING_ALLOWANCE)
    total_base_cost = _quantize_money(total_monthly_costs * months_for_calc)
    final_total_required = _quantize_money(total_base_cost + return_ticket)

    return CalculatorResult(
        rent_total=monthly_rent_and_bills,
        num_people=num_people,
        rent_per_person=rent_per_person,
        tuition_total=tuition_total,
        months_in_period=months_in_period,
        monthly_tuition_calculated=monthly_tuition,
        total_monthly_costs=total_monthly_costs,
        total_months_real=total_months_real,
        months_for_calc=months_for_calc,
        is_capped=is_capped,
        total_base_cost=total_base_cost,
        return_ticket=return_ticket,
        final_total_required=final_total_required,
    )


__all__ = [
    "CalculatorResult",
    "calculate_calculator_result",
    "convert_to_pln",
    "LIVING_ALLOWANCE",
    "MAX_MONTHS_LIVING",
    "get_eur_to_pln_rate",
    "TICKET_BORDER",
    "TICKET_NO_BORDER",
    "CURRENCY_PLN",
    "CURRENCY_EUR",
]
