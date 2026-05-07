from __future__ import annotations

from typing import Any

from django.http import Http404, HttpRequest, HttpResponse
from django.views import View


class SignupDisabledView(View):
    """Hide public signup endpoints in internal-only deployments."""

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        raise Http404
