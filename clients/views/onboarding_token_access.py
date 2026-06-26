from __future__ import annotations

import importlib

from django.http import HttpRequest, HttpResponse

from clients.constants import SELF_ONBOARDING_SLUG
from clients.models import ClientOnboardingSession

onboarding_views = importlib.import_module("clients.views.onboarding_views")
_ORIGINAL_CHECK_CLIENT_AUTH = onboarding_views.check_client_auth


def check_client_auth_for_token_link(
    request: HttpRequest,
    session: ClientOnboardingSession,
    token: str,
) -> HttpResponse | None:
    """Treat a valid raw onboarding token as a bearer credential.

    The special ``token='me'`` flow still represents the authenticated client's
    own dashboard and keeps the original login/password requirement. Staff users
    are also handled by the original function.
    """

    if token != SELF_ONBOARDING_SLUG:
        return None
    return _ORIGINAL_CHECK_CLIENT_AUTH(request, session, token)


def enable_token_link_access() -> None:
    # Runtime monkeypatch of the module-level view function; the module is loaded
    # via importlib so mypy cannot see the attribute.
    onboarding_views.check_client_auth = check_client_auth_for_token_link  # type: ignore[attr-defined]
