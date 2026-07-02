from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clients.models import Client, ClientOnboardingSession, Document
from clients.services.archive import archive_case
from clients.services.cases import create_case_for_client
from clients.services.onboarding_tokens import generate_onboarding_token
from clients.services.roles import ensure_predefined_roles
from clients.views.reminders import UPDATE_REMINDERS_LOCK_KEY


def _make_staff(email: str, role: str = "Staff"):
    ensure_predefined_roles()
    user = get_user_model().objects.create_user(email=email, password="pass", is_staff=True)
    user.groups.add(Group.objects.get(name=role))
    return user


class ArchivedDocumentAccessTests(TestCase):
    """Staff must be able to open files of documents in archived cases (audit M-2)."""

    def setUp(self) -> None:
        self.staff = _make_staff("archived-docs-staff@example.com")
        self.client_record = Client.objects.create(
            first_name="Arch",
            last_name="Ived",
            email="archived-doc-client@example.com",
            application_purpose="work",
        )
        self.case = self.client_record.cases.first()
        self.document = Document.objects.create(
            client=self.client_record,
            case=self.case,
            document_type="passport",
            file=SimpleUploadedFile("passport.pdf", b"%PDF-1.4 test %%EOF"),
        )
        archive_case(self.case, self.staff)
        self.client.force_login(self.staff)

    def test_archived_case_document_preview_is_served(self) -> None:
        response = self.client.get(
            reverse("clients:document_preview", kwargs={"doc_id": self.document.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_archived_case_document_download_is_served(self) -> None:
        response = self.client.get(
            reverse("clients:document_download", kwargs={"doc_id": self.document.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

    def test_foreign_or_missing_document_still_404(self) -> None:
        response = self.client.get(
            reverse("clients:document_preview", kwargs={"doc_id": 999999})
        )
        self.assertEqual(response.status_code, 404)


class EmailPreviewMultiCaseTests(TestCase):
    """Email previews must not merge documents of several active cases (audit M-3)."""

    def setUp(self) -> None:
        self.staff = _make_staff("email-preview-staff@example.com")
        self.client_record = Client.objects.create(
            first_name="Multi",
            last_name="Preview",
            email="multi-preview@example.com",
            application_purpose="work",
        )
        create_case_for_client(client=self.client_record, application_purpose="study")
        self.client.force_login(self.staff)

    def test_multi_case_preview_refuses_ambiguous_aggregation(self) -> None:
        response = self.client.get(
            reverse("clients:email_preview_api", kwargs={"pk": self.client_record.pk}),
            {"template_type": "missing_documents"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("несколько активных дел", response.json()["body"])


class ManualReminderRunLockTests(TestCase):
    """A second concurrent manual reminder run must be refused (audit M-1)."""

    def setUp(self) -> None:
        self.staff = _make_staff("reminder-lock-staff@example.com")
        self.client.force_login(self.staff)
        cache.delete(UPDATE_REMINDERS_LOCK_KEY)

    def tearDown(self) -> None:
        cache.delete(UPDATE_REMINDERS_LOCK_KEY)

    def test_locked_run_is_skipped_with_warning(self) -> None:
        cache.add(UPDATE_REMINDERS_LOCK_KEY, timezone.now().isoformat(), timeout=600)

        response = self.client.post(reverse("clients:run_update_reminders"), follow=True)

        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("уже выполняется" in m for m in messages), messages)
        # The lock stays in place: the skipped run must not release it.
        self.assertIsNotNone(cache.get(UPDATE_REMINDERS_LOCK_KEY))

    def test_run_releases_lock_afterwards(self) -> None:
        response = self.client.post(reverse("clients:run_update_reminders"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(cache.get(UPDATE_REMINDERS_LOCK_KEY))


class OnboardingAskQuestionRedirectTests(TestCase):
    """The client-supplied "next" must not become an open redirect."""

    def setUp(self) -> None:
        self.client_record = Client.objects.create(
            first_name="Ask",
            last_name="Question",
            email="ask-question@example.com",
            application_purpose="work",
        )
        user = get_user_model().objects.create_user(
            email="ask-question@example.com", password="clientpass123"
        )
        self.client_record.user = user
        self.client_record.save(update_fields=["user"])
        self.raw_token, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=self.client_record,
            case=self.client_record.cases.first(),
            scope="case_link",
            token_hash=hashed,
            status="active",
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(user)

    def test_external_next_is_ignored(self) -> None:
        response = self.client.post(
            reverse("clients:onboarding_ask_question", kwargs={"token": self.raw_token}),
            {"question": "When is my appointment?", "next": "https://evil.example.com/phish"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("clients:onboarding_start", kwargs={"token": self.raw_token}),
        )

    def test_local_next_is_kept(self) -> None:
        local_next = reverse(
            "clients:onboarding_review", kwargs={"token": self.raw_token}
        )
        response = self.client.post(
            reverse("clients:onboarding_ask_question", kwargs={"token": self.raw_token}),
            {"question": "When is my appointment?", "next": local_next},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], local_next)
