"""Central HTML sanitization helpers for user-provided content."""

from __future__ import annotations

from typing import Any

import nh3

ALLOWED_TAGS = {"b", "strong", "i", "em", "br", "ul", "ol", "li", "p"}
ALLOWED_ATTRIBUTES: dict[str, set[str]] = {}


def sanitize_user_html(value: Any) -> str:
    if not value:
        return ""
    return nh3.clean(
        str(value),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        link_rel="noopener noreferrer",
    )
