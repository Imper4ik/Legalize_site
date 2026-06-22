from django.shortcuts import render

from clients.views.onboarding_views import OnboardingLinkExpired


class OnboardingLinkExpiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except OnboardingLinkExpired:
            response = render(request, "clients/onboarding/expired.html")
            response.status_code = 410
            return response
