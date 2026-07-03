from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase


class TechnicalUsernameTests(TestCase):
    def test_reused_email_after_rename_gets_unique_username(self) -> None:
        """A freed-up email must stay usable for a brand-new account.

        The technical username is a deterministic digest of the email. When an
        old account changed its email away, its username still occupies the
        deterministic value; creating a new user with the same email used to
        crash with a UNIQUE constraint error on auth_user.username.
        """
        user_model = get_user_model()
        first = user_model.objects.create_user(email="piotr@example.test", password="x1y2z3w4!")
        original_username = first.username
        first.email = "piotr.corrected@example.test"
        first.save(update_fields=["email"])

        second = user_model.objects.create_user(email="piotr@example.test", password="x1y2z3w4!")

        self.assertEqual(second.email, "piotr@example.test")
        self.assertNotEqual(second.username, original_username)
        self.assertTrue(second.username.startswith("piotr-"))

    def test_deterministic_username_when_free(self) -> None:
        user_model = get_user_model()
        expected = user_model.build_technical_username("anna@example.test")
        user = user_model.objects.create_user(email="anna@example.test", password="x1y2z3w4!")
        self.assertEqual(user.username, expected)


class MarkUserEmailVerifiedTests(TestCase):
    def test_stale_allauth_row_is_reassigned_not_crashing(self) -> None:
        """A stale EmailAddress row of a renamed account must follow the email."""
        from allauth.account.models import EmailAddress

        from clients.views.onboarding_views import _mark_user_email_verified

        user_model = get_user_model()
        old = user_model.objects.create_user(email="shared@example.test", password="x1y2z3w4!")
        EmailAddress.objects.create(user=old, email="shared@example.test", primary=True, verified=True)
        old.email = "moved-away@example.test"
        old.save(update_fields=["email"])

        new = user_model.objects.create_user(email="shared@example.test", password="x1y2z3w4!")
        _mark_user_email_verified(new, "shared@example.test")

        row = EmailAddress.objects.get(email__iexact="shared@example.test")
        self.assertEqual(row.user_id, new.pk)
        self.assertTrue(row.verified)
        self.assertTrue(row.primary)
