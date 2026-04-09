from __future__ import annotations

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse


class AuthViewsTests(TestCase):
    def test_verification_sent_page_links_to_public_resend_view(self):
        response = self.client.get(reverse("account_email_verification_sent"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("account_resend_verification"))

    def test_resend_verification_page_renders_email_form(self):
        response = self.client.get(reverse("account_resend_verification"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="email"')

    def test_resend_verification_sends_message_for_unverified_email(self):
        user = get_user_model().objects.create_user(
            email="pending@example.com",
            password="StrongPass123!",
        )
        EmailAddress.objects.create(
            user=user,
            email=user.email,
            primary=True,
            verified=False,
        )

        response = self.client.post(
            reverse("account_resend_verification"),
            {"email": user.email},
        )

        self.assertRedirects(response, reverse("account_email_verification_sent"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])

    def test_resend_verification_keeps_response_generic_for_unknown_email(self):
        response = self.client.post(
            reverse("account_resend_verification"),
            {"email": "missing@example.com"},
        )

        self.assertRedirects(response, reverse("account_email_verification_sent"))
        self.assertEqual(mail.outbox, [])
