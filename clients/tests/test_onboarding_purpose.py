import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from clients.constants import DocumentType
from clients.models import Client, ClientOnboardingSession, Document, MOSApplicationData
from clients.services.onboarding_tokens import hash_onboarding_token
from clients.services.roles import ensure_predefined_roles


@override_settings(LANGUAGE_CODE="ru")
class OnboardingPurposeTests(TestCase):
    def setUp(self):
        ensure_predefined_roles()
        User = get_user_model()
        self.manager = User.objects.create_user(
            email="manager-purpose@example.com",
            password="securepassword",
            is_staff=True,
        )
        self.manager.groups.add(Group.objects.get(name="Manager"))

    def _client_with_session(self, *, application_purpose="study"):
        client = Client.objects.create(
            first_name="Purpose",
            last_name="Client",
            email=f"purpose-{uuid.uuid4().hex[:8]}@example.com",
            application_purpose=application_purpose,
            language="ru",
            assigned_staff=self.manager,
        )
        token = uuid.uuid4().hex
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hash_onboarding_token(token),
            status="created",
            expires_at=timezone.now() + timedelta(days=7),
        )
        return client, token

    def _checklist_codes(self, response):
        return {item["code"] for item in response.context["checklist"]}

    def test_existing_onboarding_link_can_change_purpose_without_changing_client_card(self):
        client, token = self._client_with_session(application_purpose="study")

        start_url = reverse("clients:onboarding_start", kwargs={"token": token})
        response = self.client.get(start_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["effective_purpose"], "study")
        self.assertIn(DocumentType.ENROLLMENT_CERTIFICATE.value, self._checklist_codes(response))
        self.assertContains(response, reverse("clients:onboarding_purpose", kwargs={"token": token}))

        response = self.client.post(
            reverse("clients:onboarding_purpose", kwargs={"token": token}),
            {"mos_purpose": "work"},
        )
        self.assertRedirects(response, start_url)

        client.refresh_from_db()
        mos_data = MOSApplicationData.objects.get(client=client)
        self.assertEqual(client.application_purpose, "study")
        self.assertEqual(mos_data.mos_purpose, "work")
        self.assertEqual(mos_data.status, "client_filling")

        response = self.client.get(start_url)
        codes = self._checklist_codes(response)
        self.assertEqual(response.context["effective_purpose"], "work")
        self.assertIn(DocumentType.EMPLOYMENT_CONTRACT.value, codes)
        self.assertNotIn(DocumentType.ENROLLMENT_CERTIFICATE.value, codes)
        self.assertContains(response, "Вы выбрали другую цель подачи")

    def test_already_sent_link_does_not_need_regeneration_to_change_purpose(self):
        client, token = self._client_with_session(application_purpose="study")
        session = ClientOnboardingSession.objects.get(client=client)
        original_session_pk = session.pk

        response = self.client.post(
            reverse("clients:onboarding_purpose", kwargs={"token": token}),
            {"mos_purpose": "work"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(ClientOnboardingSession.objects.filter(pk=original_session_pk).exists())
        self.assertEqual(MOSApplicationData.objects.get(client=client).mos_purpose, "work")

    def test_uploaded_documents_are_not_deleted_after_purpose_change(self):
        client, token = self._client_with_session(application_purpose="study")
        document = Document.objects.create(
            client=client,
            document_type=DocumentType.ENROLLMENT_CERTIFICATE.value,
            file=SimpleUploadedFile("enrollment.pdf", b"%PDF-1.4\n", content_type="application/pdf"),
        )

        response = self.client.post(
            reverse("clients:onboarding_purpose", kwargs={"token": token}),
            {"mos_purpose": "work"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())
        response = self.client.get(reverse("clients:onboarding_start", kwargs={"token": token}))
        self.assertContains(response, "Загруженные дополнительные документы")
        self.assertContains(response, reverse("clients:onboarding_document_preview", kwargs={"token": token, "doc_id": document.pk}))

    def test_locked_onboarding_cannot_change_purpose(self):
        client, token = self._client_with_session(application_purpose="study")
        mos_data = MOSApplicationData.objects.get(client=client)
        mos_data.status = "staff_review"
        mos_data.mos_purpose = "study"
        mos_data.save(update_fields=["status", "mos_purpose"])

        response = self.client.post(
            reverse("clients:onboarding_purpose", kwargs={"token": token}),
            {"mos_purpose": "work"},
        )

        self.assertEqual(response.status_code, 403)
        mos_data.refresh_from_db()
        self.assertEqual(mos_data.mos_purpose, "study")

    def test_invalid_purpose_is_rejected(self):
        client, token = self._client_with_session(application_purpose="study")

        response = self.client.post(
            reverse("clients:onboarding_purpose", kwargs={"token": token}),
            {"mos_purpose": "hacked"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(MOSApplicationData.objects.get(client=client).mos_purpose, "")

    def test_autosave_rejects_invalid_purpose_and_accepts_allowed_purpose(self):
        client, token = self._client_with_session(application_purpose="study")
        url = reverse("clients:onboarding_auto_save", kwargs={"token": token})

        response = self.client.post(url, {"mos_purpose": "hacked"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(MOSApplicationData.objects.get(client=client).mos_purpose, "")

        response = self.client.post(url, {"mos_purpose": "work"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MOSApplicationData.objects.get(client=client).mos_purpose, "work")

    def test_staff_review_shows_purpose_mismatch_warning(self):
        client, _token = self._client_with_session(application_purpose="study")
        mos_data = MOSApplicationData.objects.get(client=client)
        mos_data.mos_purpose = "work"
        mos_data.status = "staff_review"
        mos_data.save(update_fields=["mos_purpose", "status"])

        self.client.login(email="manager-purpose@example.com", password="securepassword")
        response = self.client.get(reverse("clients:admin_mos_review", kwargs={"client_id": client.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Цель в карточке клиента")
        self.assertContains(response, "Цель, выбранная клиентом")
        self.assertContains(response, "Клиент выбрал другую цель подачи")
