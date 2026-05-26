from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from clients.models import Client, ClientOnboardingSession
from clients.services.onboarding_tokens import generate_onboarding_token
from clients.views.onboarding_views import check_onboarding_session


class OnboardingSecurityTests(TestCase):
    def test_onboarding_session_stores_hash_not_raw(self):
        client = Client.objects.create(first_name="A", last_name="B", application_purpose="work")
        raw, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hashed,
            status="created",
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.assertFalse(ClientOnboardingSession.objects.filter(token_hash=raw).exists())
        self.assertIsNotNone(check_onboarding_session(raw))

    def test_invalid_or_expired_token_forbidden(self):
        client = Client.objects.create(first_name="A", last_name="B", application_purpose="work")
        raw, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hashed,
            status="created",
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.assertIsNone(check_onboarding_session(raw))
