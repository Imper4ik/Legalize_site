from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clients.models import Client, ClientOnboardingSession, MOSApplicationData
from clients.services.onboarding_tokens import hash_onboarding_token


class OnboardingStartContactTests(TestCase):
    def _client_with_session(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(email="test_contact_onb@example.com", password="secure_pwd_123")
        client = Client.objects.create(
            first_name="",
            last_name="",
            email="",
            phone="",
            user=user,
            application_purpose="study",
            language="ru",
        )
        token = "contact-token-123"
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hash_onboarding_token(token),
            status="created",
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.force_login(user)
        return client, token

    def test_get_start_page_shows_profile_indicator_and_required_contact_fields(self):
        _client, token = self._client_with_session()

        from django.utils import translation
        with translation.override('ru'):
            response = self.client.get(reverse("clients:onboarding_start", kwargs={"token": token}))

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Личный кабинет")
            self.assertContains(response, "Профиль клиента активен")
            self.assertContains(response, 'name="first_name"')
            self.assertContains(response, 'name="last_name"')
            self.assertContains(response, 'name="email"')
            self.assertContains(response, 'name="phone"')

    def test_post_start_without_required_fields_returns_errors_and_does_not_update_client(self):
        client, token = self._client_with_session()

        from django.utils import translation
        with translation.override('ru'):
            response = self.client.post(reverse("clients:onboarding_start", kwargs={"token": token}), {})

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Проверьте обязательные поля")
        client.refresh_from_db()
        self.assertEqual(client.first_name, "")
        self.assertEqual(client.last_name, "")
        self.assertEqual(client.email, "")
        self.assertEqual(client.phone, "")

    def test_post_start_with_valid_contact_updates_client_and_mos_data(self):
        client, token = self._client_with_session()
        url = reverse("clients:onboarding_start", kwargs={"token": token})

        response = self.client.post(
            url,
            {
                "first_name": "Anna",
                "last_name": "Nowak",
                "email": "anna.nowak@example.com",
                "phone": "+48123456789",
            },
        )

        self.assertRedirects(response, reverse("clients:onboarding_digital_access", kwargs={"token": token}))
        client.refresh_from_db()
        self.assertEqual(client.first_name, "Anna")
        self.assertEqual(client.last_name, "Nowak")
        self.assertEqual(client.email, "anna.nowak@example.com")
        self.assertEqual(client.phone, "+48123456789")
        mos_data = MOSApplicationData.objects.get(client=client)
        self.assertEqual(mos_data.status, "client_filling")
        self.assertEqual(mos_data.personal_data["first_name"], "Anna")
        self.assertEqual(mos_data.personal_data["last_name"], "Nowak")
        self.assertEqual(mos_data.personal_data["email"], "anna.nowak@example.com")
        self.assertEqual(mos_data.personal_data["phone"], "+48123456789")

    def test_existing_contact_values_are_compact_and_editable(self):
        client, token = self._client_with_session()
        client.first_name = "Jan"
        client.last_name = "Kowalski"
        client.email = "jan@example.com"
        client.phone = "+48600111222"
        client.save(update_fields=["first_name", "last_name", "email", "phone"])

        from django.utils import translation
        with translation.override('ru'):
            response = self.client.get(reverse("clients:onboarding_start", kwargs={"token": token}))

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Jan Kowalski")
            self.assertContains(response, "jan@example.com")
            self.assertContains(response, "+48600111222")
            self.assertContains(response, 'id="contactEditFormBottom"')
            self.assertContains(response, reverse("clients:onboarding_digital_access", kwargs={"token": token}))
            self.assertContains(response, "Продолжить анкету")

    def test_post_fingerprints_page_shows_main_document_list_open(self):
        client, token = self._client_with_session()
        mos_data, _created = MOSApplicationData.objects.get_or_create(client=client)
        mos_data.status = "fingerprints"
        mos_data.save(update_fields=["status"])

        from django.utils import translation
        with translation.override('ru'):
            response = self.client.get(reverse("clients:onboarding_start", kwargs={"token": token}))

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Ежемесячные отчеты и срочные требования")
            self.assertContains(response, "Основной список документов")
            self.assertContains(response, 'class="accordion-collapse collapse show"')
            self.assertContains(response, "onboarding-documents-card")
            self.assertContains(response, "documents-stage-note")

    def test_locked_start_page_does_not_change_contact_data(self):
        client, token = self._client_with_session()
        mos_data = MOSApplicationData.objects.get(client=client)
        mos_data.status = "staff_review"
        mos_data.save(update_fields=["status"])

        response = self.client.post(
            reverse("clients:onboarding_start", kwargs={"token": token}),
            {
                "first_name": "Blocked",
                "last_name": "Client",
                "email": "blocked@example.com",
                "phone": "+48111111111",
            },
        )

        self.assertEqual(response.status_code, 403)
        client.refresh_from_db()
        self.assertEqual(client.first_name, "")
        self.assertEqual(client.email, "")
