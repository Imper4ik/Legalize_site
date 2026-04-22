from __future__ import annotations

from django.http import Http404
from django.views import View


class SignupDisabledView(View):
    """Hide public signup endpoints in internal-only deployments."""

    def dispatch(self, request, *args, **kwargs):
        raise Http404
