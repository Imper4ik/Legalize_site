"""Regression tests for the fixes found during the July 2026 browser walkthrough
(full client+staff journey for work/study/family purposes)."""
from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clients.constants import SELF_ONBOARDING_SLUG
from clients.forms.case_client_forms import CaseForm
from clients.models import Client, ClientOnboardingSession, MOSApplicationData
from clients.services.onboarding_progress import get_case_onboarding_step
from clients.services.onboarding_tokens import generate_onboarding_token
from clients.services.roles import ensure_predefined_roles
from clients.services.wezwanie_parser import _find_decision_date


class OnboardingTimelineStepTests(TestCase):
    """A fingerprints_date on the case must not pin the portal timeline to the
    fingerprints step after the case moved to waiting/decision."""

    def setUp(self) -> None:
        self.client_record = Client.objects.create(
            first_name="Timeline",
            last_name="Client",
            email="timeline-client@example.com",
            application_purpose="work",
        )
        self.case = self.client_record.cases.first()
        self.case.fingerprints_date = timezone.localdate() - timedelta(days=10)
        self.case.save(update_fields=["fingerprints_date"])
        self.mos, _ = MOSApplicationData.objects.get_or_create(
            client=self.client_record, case=self.case
        )

    def _step_for(self, status: str) -> int:
        self.mos.status = status
        self.mos.save(update_fields=["status"])
        return get_case_onboarding_step(
            client=self.client_record, case=self.case, mos_data=self.mos, checklist=[]
        )

    def test_fingerprints_status_stays_on_step_8(self) -> None:
        self.assertEqual(self._step_for("fingerprints"), 8)

    def test_waiting_decision_reaches_step_9_despite_fingerprints_date(self) -> None:
        self.assertEqual(self._step_for("waiting_decision"), 9)

    def test_decision_received_reaches_step_10_despite_fingerprints_date(self) -> None:
        self.assertEqual(self._step_for("decision_received"), 10)
        self.assertEqual(self._step_for("closed"), 10)


class CaseFormDecisionDateTests(TestCase):
    """Staff must be able to record the decision date manually — decisions often
    arrive by post, so the OCR confirmation cannot be the only entry point."""

    def setUp(self) -> None:
        self.client_record = Client.objects.create(
            first_name="Decision",
            last_name="Manual",
            email="decision-manual@example.com",
            application_purpose="work",
        )
        self.case = self.client_record.cases.first()

    def test_form_exposes_and_saves_decision_date(self) -> None:
        form = CaseForm(
            data={
                "application_purpose": "work",
                "family_role": "",
                "workflow_stage": self.case.workflow_stage,
                "submission_date": "01.06.2026",
                "fingerprints_date": "10.06.2026",
                "decision_date": "30.06.2026",
                "version": self.case.version,
            },
            instance=self.case,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.decision_date, date(2026, 6, 30))


class CompletedOnboardingLinkRedirectTests(TestCase):
    """A completed onboarding link must route the client onward, not 403."""

    def setUp(self) -> None:
        self.client_record = Client.objects.create(
            first_name="Completed",
            last_name="Link",
            email="completed-link@example.com",
            application_purpose="work",
        )
        self.user = get_user_model().objects.create_user(
            email="completed-link@example.com", password="clientpass123"
        )
        self.client_record.user = self.user
        self.client_record.save(update_fields=["user"])
        self.raw_token, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=self.client_record,
            case=self.client_record.cases.first(),
            scope="case_link",
            token_hash=hashed,
            status="completed",
            completed_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.start_url = reverse(
            "clients:onboarding_start", kwargs={"token": self.raw_token}
        )

    def test_logged_in_client_is_redirected_to_portal(self) -> None:
        self.client.force_login(self.user)
        response = self.client.get(self.start_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("clients:onboarding_start", kwargs={"token": SELF_ONBOARDING_SLUG}),
        )

    def test_anonymous_client_is_redirected_to_login(self) -> None:
        response = self.client.get(self.start_url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("account_login")))

    def test_invalid_token_still_forbidden(self) -> None:
        response = self.client.get(
            reverse("clients:onboarding_start", kwargs={"token": "bogus-token-value"})
        )
        self.assertEqual(response.status_code, 403)


class ClientCreateRedirectTests(TestCase):
    """After creating a client, staff should land on the new client's card."""

    def setUp(self) -> None:
        ensure_predefined_roles()
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            email="create-redirect-staff@example.com",
            password="securepassword",
            is_staff=True,
        )
        self.staff.groups.add(Group.objects.get(name="Staff"))
        self.client.force_login(self.staff)

    def test_create_redirects_to_client_detail(self) -> None:
        response = self.client.post(
            reverse("clients:client_add"),
            {
                "first_name": "Redirect",
                "last_name": "Target",
                "email": "redirect-target@example.com",
                "phone": "+48111222333",
                "citizenship": "UA",
                "application_purpose": "work",
                "language": "pl",
                "status": "new",
            },
        )
        self.assertEqual(response.status_code, 302)
        created = Client.objects.get(email_hash=Client.hash_email("redirect-target@example.com"))
        self.assertEqual(
            response["Location"],
            reverse("clients:client_detail", kwargs={"pk": created.pk}),
        )


class DecisionDateParserTests(TestCase):
    """The parser must extract the date of an actually issued decision."""

    def test_decyzja_z_dnia(self) -> None:
        self.assertEqual(
            _find_decision_date("W nawiązaniu do decyzji z dnia 15.06.2026 r. informujemy..."),
            date(2026, 6, 15),
        )

    def test_decyzja_nr_z_dnia(self) -> None:
        self.assertEqual(
            _find_decision_date("Decyzja nr WSC/123/2026 z dnia 01.02.2026 w sprawie..."),
            date(2026, 2, 1),
        )

    def test_wydano_decyzje_dnia(self) -> None:
        self.assertEqual(
            _find_decision_date("Wydano decyzję dnia 03.03.2026."),
            date(2026, 3, 3),
        )

    def test_deadline_phrasing_still_works(self) -> None:
        self.assertEqual(
            _find_decision_date("Decyzja zostanie podjęta do dnia 30.09.2026."),
            date(2026, 9, 30),
        )
