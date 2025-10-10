"""HTTP-related helper utilities for the project."""
from __future__ import annotations

from django.http import HttpRequest


def request_is_ajax(request: HttpRequest) -> bool:
    """Return ``True`` when a request expects an AJAX/JSON response."""
    header = request.headers.get("x-requested-with")
    if not header:
        header = request.META.get("HTTP_X_REQUESTED_WITH")
    if header and header.lower() == "xmlhttprequest":
        return True

    accepts = request.headers.get("accept", "")
    if "application/json" in accepts.lower():
        return True

    if request.headers.get("sec-fetch-mode") == "cors" and request.method != "GET":
        return True

    return False
