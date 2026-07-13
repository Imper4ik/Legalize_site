from __future__ import annotations

from allauth.mfa.models import Authenticator
from django.test import TestCase, override_settings
from django.urls import reverse

from clients.testing.factories import TEST_USER_CREDENTIAL, create_test_user
from legalize_site.checks import STAFF_MFA_WARNING_ID, staff_mfa_check


class MfaEnrollmentPageTests(TestCase):
    def test_staff_can_open_mfa_settings(self):
        staff = create_test_user(role="Staff")
        self.client.login(email=staff.email, password=TEST_USER_CREDENTIAL)
        response = self.client.get(reverse("mfa_index"))
        self.assertEqual(response.status_code, 200)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("mfa_index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])


class StaffMfaCheckTests(TestCase):
    @override_settings(IS_PRODUCTION=True)
    def test_unenrolled_staff_triggers_warning(self):
        create_test_user(role="Staff")
        ids = [message.id for message in staff_mfa_check()]
        self.assertIn(STAFF_MFA_WARNING_ID, ids)

    @override_settings(IS_PRODUCTION=True)
    def test_enrolled_staff_is_silent(self):
        staff = create_test_user(role="Staff")
        Authenticator.objects.create(
            user=staff, type=Authenticator.Type.TOTP, data={"secret": "dummy"}
        )
        self.assertEqual(staff_mfa_check(), [])

    @override_settings(IS_PRODUCTION=False)
    def test_non_production_is_silent(self):
        create_test_user(role="Staff")
        self.assertEqual(staff_mfa_check(), [])
