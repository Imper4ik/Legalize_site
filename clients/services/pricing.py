"""Service layer utilities for pricing lookup.

Centralizing pricing logic keeps it reusable between views and tasks
while avoiding duplication when the list of services grows.
"""
from __future__ import annotations

from typing import Mapping

SERVICE_PRICES: Mapping[str, float] = {
    "study_service": 1400.00,
    "work_service": 1800.00,
    "consultation": 180.00,
}


def get_service_price(service_value: str) -> float:
    """Return the configured price for the given service code."""
    return SERVICE_PRICES.get(service_value, 0.00)
