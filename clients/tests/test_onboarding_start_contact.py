from datetime import timedelta
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from clients.constants import DocumentType
from clients.models import Client, ClientOnboardingSession, Document, MOSApplicationData
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

        with translation.override("ru"):
            response = self.client.get(reverse("clients:onboarding_start", kwargs={"token": token}))

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Личный кабинет")
            self.assertContains(response, "Сейчас от вас нужно")
            self.assertContains(response, "Личный кабинет активен")
            self.assertContains(response, 'name="first_name"')
            self.assertContains(response, 'name="last_name"')
            self.assertContains(response, 'name="email"')
            self.assertContains(response, 'name="phone"')

    def test_post_start_without_required_fields_returns_errors_and_does_not_update_client(self):
        client, token = self._client_with_session()

        from django.utils import translation

        with translation.override("ru"):
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

        with translation.override("ru"):
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

        with translation.override("ru"):
            response = self.client.get(reverse("clients:onboarding_start", kwargs={"token": token}))

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Что нужно дослать сейчас")
            self.assertContains(response, "Остальные документы по делу")
            self.assertContains(response, 'class="accordion-collapse collapse show"')
            self.assertContains(response, "onboarding-documents-card")
            self.assertContains(response, "documents-stage-note")
            self.assertContains(response, "uploadFingerprintInvitationModal")
            self.assertContains(response, "Сохранить контактные данные")

    def _work_client_with_session(self, token="resupply-token-1"):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(email=f"{token}@example.com", password="secure_pwd_123")
        client = Client.objects.create(
            first_name="Re",
            last_name="Supply",
            email="",
            phone="",
            user=user,
            application_purpose="work",
            language="ru",
        )
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hash_onboarding_token(token),
            status="created",
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.force_login(user)
        return client, token

    def test_recurring_zus_keeps_upload_and_lists_all_months(self):
        from datetime import date

        from django.utils import translation

        from clients.testing.factories import create_test_document

        client, token = self._work_client_with_session()
        mos_data, _ = MOSApplicationData.objects.get_or_create(client=client)
        mos_data.status = "fingerprints"
        mos_data.save(update_fields=["status"])

        zus = DocumentType.ZUS_RCA_OR_INSURANCE.value
        d1 = create_test_document(client, doc_type=zus, verified=True, zus_period_month=date(2026, 4, 1))
        d2 = create_test_document(client, doc_type=zus, verified=True, zus_period_month=date(2026, 5, 1))

        with translation.override("ru"):
            response = self.client.get(reverse("clients:onboarding_start", kwargs={"token": token}))

        self.assertEqual(response.status_code, 200)
        # Upload control stays available even though a month is already accepted.
        self.assertContains(response, "Загрузить ещё месяц")
        self.assertContains(response, "Загружено месяцев:")
        # Every uploaded month is listed (one calendar row per month).
        self.assertContains(response, "bi-calendar3", count=2)
        # And the upload modal is rendered despite the document being uploaded.
        self.assertContains(response, 'id="uploadModal')
        self.assertTrue(d1.pk and d2.pk)

    def test_expired_document_offers_resupply(self):
        from datetime import date, timedelta as _td

        from django.utils import translation

        from clients.testing.factories import create_test_document

        client, token = self._work_client_with_session(token="resupply-token-2")
        mos_data, _ = MOSApplicationData.objects.get_or_create(client=client)
        mos_data.status = "fingerprints"
        mos_data.save(update_fields=["status"])

        create_test_document(
            client,
            doc_type=DocumentType.EMPLOYMENT_CONTRACT.value,
            verified=True,
            expiry_date=date.today() - _td(days=1),
        )

        with translation.override("ru"):
            response = self.client.get(reverse("clients:onboarding_start", kwargs={"token": token}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Обновить документ")

    def test_locked_post_fingerprints_contact_gap_can_be_completed(self):
        client, token = self._client_with_session()
        mos_data, _created = MOSApplicationData.objects.get_or_create(client=client)
        mos_data.status = "fingerprints"
        mos_data.save(update_fields=["status"])

        response = self.client.post(
            reverse("clients:onboarding_start", kwargs={"token": token}),
            {
                "first_name": "Darya",
                "last_name": "Afanasenka",
                "email": "afanasenko860@gmail.com",
                "phone": "571 381 041",
            },
        )

        self.assertRedirects(response, reverse("clients:onboarding_start", kwargs={"token": token}))
        client.refresh_from_db()
        self.assertEqual(client.first_name, "Darya")
        self.assertEqual(client.last_name, "Afanasenka")
        self.assertEqual(client.email, "afanasenko860@gmail.com")
        self.assertEqual(client.phone, "571 381 041")

        mos_data.refresh_from_db()
        self.assertEqual(mos_data.status, "fingerprints")
        self.assertEqual(mos_data.personal_data["first_name"], "Darya")
        self.assertEqual(mos_data.personal_data["last_name"], "Afanasenka")
        self.assertEqual(mos_data.personal_data["email"], "afanasenko860@gmail.com")
        self.assertEqual(mos_data.personal_data["phone"], "571 381 041")

        from django.utils import translation

        with translation.override("ru"):
            response = self.client.get(reverse("clients:onboarding_start", kwargs={"token": token}))
            self.assertContains(response, "Контактные данные сохранены")
            self.assertNotContains(response, "Внимание: Заполните контактные данные")

    def test_locked_start_page_does_not_change_contact_data(self):
        client, token = self._client_with_session()
        client.first_name = "Existing"
        client.last_name = "Client"
        client.email = "existing@example.com"
        client.phone = "+48111111111"
        client.save(update_fields=["first_name", "last_name", "email", "phone"])

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
        self.assertEqual(client.first_name, "Existing")
        self.assertEqual(client.email, "existing@example.com")

    def _png_upload(self, name="confirmation.png"):
        image = Image.new("RGB", (8, 8), color="white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def test_new_card_application_block_is_visible(self):
        _client, token = self._client_with_session()

        from django.utils import translation

        with translation.override("ru"):
            response = self.client.get(reverse("clients:onboarding_start", kwargs={"token": token}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Новое заявление на карту пребывания")
        self.assertContains(response, 'name="action" value="new_card_application"')
        self.assertContains(response, 'name="new_card_application_status"')
        self.assertContains(response, 'name="new_card_confirmation_file"')

    def test_new_card_application_post_saves_data_and_confirmation_file(self):
        client, token = self._client_with_session()
        today = timezone.localdate()

        response = self.client.post(
            reverse("clients:onboarding_start", kwargs={"token": token}),
            {
                "action": "new_card_application",
                "new_card_application_status": MOSApplicationData.NEW_CARD_STATUS_YES,
                "new_card_case_number": "WSC-II-123/2026",
                "new_card_submitted_at": today.isoformat(),
                "new_card_comment": "Submitted through MOS.",
                "new_card_confirmation_file": self._png_upload(),
            },
        )

        self.assertRedirects(response, reverse("clients:onboarding_start", kwargs={"token": token}))
        mos_data = MOSApplicationData.objects.get(client=client)
        self.assertEqual(mos_data.new_residence_card_application_status, MOSApplicationData.NEW_CARD_STATUS_YES)
        self.assertEqual(str(mos_data.new_residence_card_case_number), "WSC-II-123/2026")
        self.assertEqual(mos_data.new_residence_card_submitted_at, today)
        self.assertEqual(mos_data.new_residence_card_comment, "Submitted through MOS.")
        self.assertTrue(
            Document.objects.filter(
                client=client,
                document_type=DocumentType.NEW_RESIDENCE_CARD_APPLICATION_CONFIRMATION.value,
            ).exists()
        )

    def test_new_card_application_rejects_future_submission_date(self):
        client, token = self._client_with_session()
        future_date = timezone.localdate() + timedelta(days=1)

        from django.utils import translation

        with translation.override("ru"):
            response = self.client.post(
                reverse("clients:onboarding_start", kwargs={"token": token}),
                {
                    "action": "new_card_application",
                    "new_card_application_status": MOSApplicationData.NEW_CARD_STATUS_YES,
                    "new_card_submitted_at": future_date.isoformat(),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Дата подачи не может быть в будущем")
        mos_data = MOSApplicationData.objects.get(client=client)
        self.assertEqual(mos_data.new_residence_card_application_status, "")
        self.assertIsNone(mos_data.new_residence_card_submitted_at)

    def test_support_email_is_rendered_as_compact_help_block(self):
        _client, token = self._client_with_session()
        from django.utils import translation

        with self.settings(DEFAULT_FROM_EMAIL="support@example.test"):
            with translation.override("ru"):
                response = self.client.get(reverse("clients:onboarding_start", kwargs={"token": token}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Служба поддержки")
        self.assertContains(response, "support@example.test")
        self.assertContains(response, 'href="mailto:support@example.test"')
