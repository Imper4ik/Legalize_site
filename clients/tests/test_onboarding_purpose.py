import base64
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from clients.constants import DocumentType
from clients.models import (
    Client,
    ClientOnboardingSession,
    Document,
    DocumentProcessingJob,
    MOSApplicationData,
    StaffTask,
)
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
        User = get_user_model()
        user = User.objects.create_user(email=client.email, password="password123")
        client.user = user
        client.save()
        self.client.force_login(user)

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
        self.assertEqual(response.context["effective_purpose"], "study")
        self.assertIn(DocumentType.ENROLLMENT_CERTIFICATE.value, codes)
        self.assertNotIn(DocumentType.EMPLOYMENT_CONTRACT.value, codes)
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
        self.assertContains(response, "Загружено")
        self.assertContains(response, reverse("clients:onboarding_document_preview", kwargs={"token": token, "doc_id": document.pk}))


    def test_client_can_upload_fingerprint_invitation_and_staff_gets_task(self):
        client, token = self._client_with_session(application_purpose="study")
        upload_url = reverse(
            "clients:onboarding_document_upload",
            kwargs={"token": token, "doc_type": DocumentType.WEZWANIE.value},
        )

        response = self.client.post(
            upload_url,
            {"file": SimpleUploadedFile("wezwanie.png", base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"), content_type="image/png")},
        )

        self.assertEqual(response.status_code, 302)
        document = Document.objects.get(client=client, document_type=DocumentType.WEZWANIE.value)
        task = StaffTask.objects.get(client=client, document=document)
        self.assertEqual(task.assignee, self.manager)
        self.assertEqual(task.priority, "high")
        self.assertIn("отпечатки", task.title.lower())
        self.assertIn("Откройте документ", task.description)
        self.assertIn("вручную внесите дату, время и место", task.description)
        self.assertIn(reverse("clients:document_preview", kwargs={"doc_id": document.pk}), task.description)
        self.assertIn(reverse("clients:client_edit", kwargs={"pk": client.pk}), task.description)
        self.assertFalse(DocumentProcessingJob.objects.filter(document=document).exists())

        client.refresh_from_db()
        self.assertIsNone(client.fingerprints_date)
        self.assertIsNone(client.fingerprints_time)
        self.assertIn(client.fingerprints_location, (None, ""))

        self.client.force_login(self.manager)
        schedule_response = self.client.get(reverse("clients:fingerprints_schedule"))

        self.assertEqual(schedule_response.status_code, 200)
        self.assertNotIn(client, schedule_response.context["upcoming_appointments"])

        self.client.force_login(client.user)
        response = self.client.get(reverse("clients:onboarding_start", kwargs={"token": token}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Приглашение на отпечатки пальцев")
        self.assertContains(response, "Загрузить новый")
        self.assertContains(response, reverse("clients:onboarding_document_preview", kwargs={"token": token, "doc_id": document.pk}))

    def test_onboarding_document_source_hints_are_translated_for_client_page(self):
        _client, token = self._client_with_session(application_purpose="work")
        expectations = {
            "en": (
                "Scan or photograph your valid passport.",
                "ZUS RCA can be downloaded from ZUS PUE/eZUS",
                "Отсканируйте или сфотографируйте действующий паспорт.",
            ),
            "pl": (
                "Zeskanuj albo sfotografuj ważny paszport.",
                "ZUS RCA można pobrać w ZUS PUE/eZUS",
                "Отсканируйте или сфотографируйте действующий паспорт.",
            ),
            "ru": (
                "Отсканируйте или сфотографируйте действующий паспорт.",
                "ZUS RCA можно скачать в ZUS PUE/eZUS",
                "Scan or photograph your valid passport.",
            ),
        }

        for language, (passport_hint, zus_hint, absent_text) in expectations.items():
            with self.subTest(language=language), override(language):
                response = self.client.get(reverse("clients:onboarding_start", kwargs={"token": token}))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, passport_hint)
                self.assertContains(response, zus_hint)
                self.assertNotContains(response, absent_text)
                if language == "ru":
                    self.assertContains(response, "Карта побыту")
                    self.assertNotContains(response, "Карта пребывания")
                    self.assertNotContains(response, "Карта проживания")

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

    def test_staff_can_generate_existing_client_link_with_family_purpose(self):
        client = Client.objects.create(
            first_name="Existing",
            last_name="Client",
            email="existing-purpose@example.com",
            application_purpose="study",
            language="ru",
            assigned_staff=self.manager,
        )

        self.client.login(email="manager-purpose@example.com", password="securepassword")
        response = self.client.post(
            reverse("clients:generate_onboarding_link", kwargs={"client_id": client.pk}),
            {"application_purpose": "family_spouse"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        raw_token = response.json()["link"].rstrip("/").split("/")[-1]
        client.refresh_from_db()
        self.assertEqual(client.application_purpose, "family")
        self.assertEqual(client.family_role, "family_spouse")
        self.assertEqual(client.get_document_requirement_purpose(), "family_spouse")
        self.assertTrue(ClientOnboardingSession.objects.filter(client=client, token_hash=hash_onboarding_token(raw_token)).exists())
        self.assertEqual(MOSApplicationData.objects.get(client=client).mos_purpose, "")

    def test_travel_step_preserves_canonical_purpose_when_not_changed(self):
        client, token = self._client_with_session(application_purpose="study")
        mos_data = MOSApplicationData.objects.get(client=client)
        mos_data.mos_purpose = "work"
        mos_data.save(update_fields=["mos_purpose"])

        response = self.client.post(
            reverse("clients:onboarding_travel", kwargs={"token": token}),
            {
                "is_in_poland": "yes",
                "last_entry_date": "2026-01-01",
                "stay_basis": "visa",
                "was_in_poland_before": "no",
                "has_insurance": "yes",
                "has_stable_income": "yes",
                "previous_stays": "",
                "travel_history": "No trips",
            },
        )

        self.assertEqual(response.status_code, 302)
        mos_data.refresh_from_db()
        self.assertEqual(mos_data.mos_purpose, "work")

    def test_staff_can_accept_client_selected_family_purpose(self):
        client, _token = self._client_with_session(application_purpose="study")
        mos_data = MOSApplicationData.objects.get(client=client)
        mos_data.mos_purpose = "family_child"
        mos_data.status = "staff_review"
        mos_data.save(update_fields=["mos_purpose", "status"])

        self.client.login(email="manager-purpose@example.com", password="securepassword")
        response = self.client.post(
            reverse("clients:admin_mos_review", kwargs={"client_id": client.pk}),
            {"action": "accept_client_purpose"},
        )

        self.assertEqual(response.status_code, 302)
        client.refresh_from_db()
        self.assertEqual(client.application_purpose, "family")
        self.assertEqual(client.family_role, "family_child")
        self.assertEqual(client.get_document_requirement_purpose(), "family_child")

    def test_staff_gets_attention_notification_for_client_purpose_change(self):
        cache.clear()
        client, _token = self._client_with_session(application_purpose="study")
        other_client, _other_token = self._client_with_session(application_purpose="study")
        other_client.first_name = "NoChange"
        other_client.email = "no-change-purpose@example.com"
        other_client.save(update_fields=["first_name", "email"])
        mos_data = MOSApplicationData.objects.get(client=client)
        mos_data.mos_purpose = "work"
        mos_data.status = "client_filling"
        mos_data.save(update_fields=["mos_purpose", "status"])

        self.client.login(email="manager-purpose@example.com", password="securepassword")
        list_url = reverse("clients:client_list")
        response = self.client.get(list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["purpose_change_count"], 1)
        self.assertContains(response, f"{list_url}?onboarding=purpose_change")
        self.assertContains(response, "Смена основания")
        self.assertContains(response, reverse("clients:admin_mos_review", kwargs={"client_id": client.pk}))

        filtered_response = self.client.get(list_url, {"onboarding": "purpose_change"})
        self.assertEqual(filtered_response.status_code, 200)
        self.assertContains(filtered_response, "Показаны клиенты, где клиент изменил основание подачи")
        self.assertContains(filtered_response, "Purpose")
        self.assertNotContains(filtered_response, "NoChange")

        detail_response = self.client.get(reverse("clients:client_detail", kwargs={"pk": client.pk}))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Клиент изменил основание подачи")
        self.assertContains(detail_response, "Подтвердить или проверить")
