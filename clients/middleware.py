from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from clients.views.onboarding_views import OnboardingLinkExpired


class OnboardingLinkExpiredMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        try:
            return self.get_response(request)
        except OnboardingLinkExpired:
            response = render(request, "clients/onboarding/expired.html")
            response.status_code = 410
            return response
