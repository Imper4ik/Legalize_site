"""Central HTML sanitization helpers for user-provided content."""

from __future__ import annotations

from typing import Any

import bleach

# TODO: replace bleach with nh3 or another maintained sanitizer after parity tests.
ALLOWED_TAGS = ["b", "strong", "i", "em", "br", "ul", "ol", "li", "p"]
ALLOWED_ATTRIBUTES: dict[str, list[str]] = {}
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def sanitize_user_html(value: Any) -> str:
    if not value:
        return ""
    return bleach.clean(
        str(value),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
