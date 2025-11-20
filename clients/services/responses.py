"""Utilities for consistent JSON responses and response format detection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.translation import gettext as _

from legalize_site.utils.http import request_is_ajax


NO_STORE_HEADER = "no-store"


def apply_no_store(response: HttpResponse) -> HttpResponse:
    """Add a ``Cache-Control: no-store`` header to the response."""
    response["Cache-Control"] = NO_STORE_HEADER
    return response


def json_no_store(payload: Dict[str, Any], *, status: int = 200) -> JsonResponse:
    """Return a JSON response with cache disabled."""
    response = JsonResponse(payload, status=status)
    return apply_no_store(response)


@dataclass
class ResponseHelper:
    """Determine the expected response format and build consistent JSON payloads."""

    request: HttpRequest

    @property
    def expects_json(self) -> bool:
        return request_is_ajax(self.request)

    def success(self, message: Optional[str] = None, **extra: Any) -> JsonResponse:
        payload: Dict[str, Any] = {"status": "success", **extra}
        if message:
            payload.setdefault("message", message)
        return json_no_store(payload)

    def error(self, message: Optional[str] = None, *, status: int = 400, errors: Any = None,
              **extra: Any) -> JsonResponse:
        payload: Dict[str, Any] = {"status": "error", **extra}
        if errors is not None:
            payload["errors"] = errors
        if message:
            payload.setdefault("message", message)
        return json_no_store(payload, status=status)

    def forbidden(self) -> JsonResponse:
        return self.error(message=_('Доступ запрещен'), status=403)
