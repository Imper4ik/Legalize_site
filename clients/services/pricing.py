"""Service layer utilities for pricing lookup.

Centralizing pricing logic keeps it reusable between views and tasks
while avoiding duplication when the list of services grows.
"""
from __future__ import annotations

import logging
from typing import Mapping

logger = logging.getLogger(__name__)

SERVICE_PRICES: Mapping[str, float] = {
    "study_service": 1400.00,
    "work_service": 1800.00,
    "consultation": 180.00,
}


def get_service_price(service_value: str) -> float:
    """Return the configured price for the given service code from DB with fallback."""
    from clients.models import ServicePrice
    try:
        sp = ServicePrice.objects.filter(service_code=service_value).first()
        if sp:
            return float(sp.price)
    except Exception as e:
        logger.warning(f"Could not fetch ServicePrice for {service_value}: {e}")

    return SERVICE_PRICES.get(service_value, 0.00)
