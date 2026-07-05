import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from clients.forms import ClientForm
from clients.models import Client, ClientOnboardingSession, Document, DocumentRequirement, MOSApplicationData
from clients.services.onboarding_tokens import hash_onboarding_token
from clients.services.roles import ensure_predefined_roles


@override_settings(LANGUAGE_CODE="ru")
class QuickOnboardingTests(TestCase):
    def setUp(self):
        ensure_predefined_roles()
        User = get_user_model()
        self.manager = User.objects.create_user(
            email="manager@example.com",
            password="securepassword",
            is_staff=True
        )
        self.manager.groups.add(Group.objects.get(name="Manager"))
        self.client_agent = self.client
        self.client_agent.login(email="manager@example.com", password="securepassword")

    def test_client_form_optional_fields(self):
        """Verify that ClientForm validates successfully when email, phone, and citizenship are left blank."""
        form_data = {
            "first_name": "Тест",
            "last_name": "Тестов",
            "email": "",
            "phone": "",
            "citizenship": "",
            "application_purpose": "study",
            "language": "pl",
            "status": "new",
            "workflow_stage": "new_client",
        }
        form = ClientForm(data=form_data, user=self.manager)
        self.assertTrue(form.is_valid(), form.errors)
        client = form.save()
        self.assertEqual(client.first_name, "Тест")
        self.assertEqual(client.email, "")
        self.assertEqual(client.phone, "")
        self.assertEqual(client.citizenship, "")

    def test_quick_create_client_onboarding_view(self):
        """Verify that the quick onboarding view creates a Client, onboarding session, and returns a JSON link."""
        url = reverse("clients:quick_create_client_onboarding")
        response = self.client_agent.post(url, {
            "first_name": "Быстрый",
            "last_name": "Клиент",
            "email": "quick@example.com",
            "phone": "+48999999999",
            "language": "ru",
            "application_purpose": "work",
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("link", data)
        self.assertIn("Клиент добавлен", data["message"])

        # Check that client exists
        client = Client.objects.get(email="quick@example.com")
        self.assertEqual(client.first_name, "Быстрый")
        self.assertEqual(client.last_name, "Клиент")
        self.assertEqual(client.phone, "+48999999999")
        self.assertEqual(client.language, "ru")
        self.assertEqual(client.application_purpose, "work")

        # Check session exists
        session = ClientOnboardingSession.objects.filter(client=client).first()
        self.assertIsNotNone(session)
        raw_token = data["link"].rstrip('/').split('/')[-1]
        self.assertEqual(hash_onboarding_token(raw_token), session.token_hash)

    def test_quick_create_maps_family_purpose_to_family_role(self):
        url = reverse("clients:quick_create_client_onboarding")
        response = self.client_agent.post(url, {
            "email": "quick-family@example.com",
            "application_purpose": "family_child",
        })

        self.assertEqual(response.status_code, 200)
        client = Client.objects.get(email="quick-family@example.com")
        self.assertEqual(client.application_purpose, "family")
        self.assertEqual(client.family_role, "family_child")
        self.assertEqual(client.get_document_requirement_purpose(), "family_child")

    def test_quick_create_rejects_invalid_purpose(self):
        response = self.client_agent.post(
            reverse("clients:quick_create_client_onboarding"),
            {"application_purpose": "hacked"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "error")

    def test_client_list_quick_link_asks_for_purpose(self):
        response = self.client_agent.get(reverse("clients:client_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-bs-target="#quickOnboardingModal"')
        self.assertContains(response, 'id="quickOnboardingModal"')
        self.assertContains(response, 'id="quick-onboarding-purpose"')
        self.assertContains(response, 'value="family_spouse"')
        self.assertContains(response, 'value="family_child"')

    def test_onboarding_start_post_redirects_to_first_step(self):
        """Verify that a POST request to onboarding_start redirects to onboarding_digital_access."""
        client = Client.objects.create(
            first_name="Новый",
            last_name="Клиент",
        )
        token = uuid.uuid4().hex
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hash_onboarding_token(token),
            status="created",
            expires_at=timezone.now() + timedelta(days=7)
        )

        url = reverse("clients:onboarding_start", kwargs={"token": token})
        response = self.client_agent.post(url, {
            "first_name": "Новый",
            "last_name": "Клиент",
            "email": "noviy.klient@example.com",
            "phone": "+48123456789",
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("clients:onboarding_digital_access", kwargs={"token": token}))

    def test_onboarding_start_upload_ui_requires_preview_confirmation(self):
        DocumentRequirement.objects.filter(application_purpose="work", document_type__in=["passport_scan", "photo_scan"]).delete()
        DocumentRequirement.objects.create(
            application_purpose="work",
            document_type="passport_scan",
            custom_name="Passport scan",
            position=1,
        )
        DocumentRequirement.objects.create(
            application_purpose="work",
            document_type="photo_scan",
            custom_name="Photo scan",
            position=2,
        )
        client = Client.objects.create(
            first_name="Upload",
            last_name="Client",
            application_purpose="work",
            language="en",
        )
        token = uuid.uuid4().hex
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hash_onboarding_token(token),
            status="created",
            expires_at=timezone.now() + timedelta(days=7),
        )
        document = Document.objects.create(
            client=client,
            document_type="passport_scan",
            file=SimpleUploadedFile("passport.pdf", b"%PDF-1.4\n", content_type="application/pdf"),
        )

        response = self.client_agent.get(reverse("clients:onboarding_start", kwargs={"token": token}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("clients:onboarding_document_preview", kwargs={"token": token, "doc_id": document.pk}),
        )
        self.assertContains(response, "onboarding-upload-preview")
        self.assertContains(response, "onboarding-upload-confirm")
        self.assertContains(response, 'class="btn btn-primary onboarding-upload-submit"')
        self.assertContains(response, 'data-loading-text=')
        self.assertContains(response, 'disabled')

    def test_onboarding_step1_syncs_contact_fields_only(self):
        """Step 1 updates staff-visible contact fields immediately, keeping legal fields in MOS draft."""
        client = Client.objects.create(
            first_name="Placeholder",
            last_name="Client",
            language="pl",
        )
        token = uuid.uuid4().hex
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hash_onboarding_token(token),
            status="created",
            expires_at=timezone.now() + timedelta(days=7),
        )

        response = self.client_agent.post(reverse("clients:onboarding_passport", kwargs={"token": token}), {
            "first_name": "Ivan",
            "last_name": "Ivanov",
            "phone": "+48111222333",
            "email": "ivan@example.com",
            "birth_date": "1990-05-15",
            "citizenship": "BY",
            "document_number": "MP1234567",
            "expiry_date": "2030-05-15",
        })
        self.assertEqual(response.status_code, 302)

        client.refresh_from_db()
        self.assertEqual(client.first_name, "Ivan")
        self.assertEqual(client.last_name, "Ivanov")
        self.assertEqual(client.phone, "+48111222333")
        self.assertEqual(client.email, "ivan@example.com")
        self.assertEqual(client.citizenship, "")
        self.assertIsNone(client.passport_num)
        self.assertIsNone(client.birth_date)

        mos_data = MOSApplicationData.objects.get(client=client)
        self.assertEqual(mos_data.personal_data["citizenship"], "BY")
        self.assertEqual(mos_data.personal_data["birth_date"], "1990-05-15")
        self.assertEqual(mos_data.passport_data["document_number"], "MP1234567")

    @override_settings(DEFAULT_FROM_EMAIL="office@example.com", EMAIL_REPLY_TO="office@example.com")
    def test_onboarding_completion_notifies_staff(self):
        """Completing onboarding emails the shared office mailbox.

        Staff is not assigned to clients (spec §2), so the notification goes to
        the office staff recipients, never to a per-client "responsible" staffer.
        """
        client = Client.objects.create(
            first_name="Иван",
            last_name="Иванов",
            language="pl",
        )
        token = uuid.uuid4().hex
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hash_onboarding_token(token),
            status="created",
            expires_at=timezone.now() + timedelta(days=7)
        )
        # Ensure MOSApplicationData exists
        mos_data = MOSApplicationData.objects.get(client=client)

        declarations_url = reverse("clients:onboarding_declarations", kwargs={"token": token})

        mail.outbox.clear()
        response = self.client_agent.post(declarations_url, {
            "criminal_record": "no",
            "tax_arrears": "no",
            "rodo_consent": "on",  # RODO: completing onboarding now requires consent.
        })
        self.assertEqual(response.status_code, 302) # Redirect to review
        review_response = self.client_agent.get(response["Location"])
        self.assertEqual(review_response.status_code, 200)

        # Verify status
        mos_data.refresh_from_db()
        self.assertEqual(mos_data.status, "client_completed")

        # Verify email was sent to the office mailbox, not the logged-in manager.
        self.assertGreaterEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("office@example.com", email.to)
        self.assertNotIn(self.manager.email, email.to)
        self.assertIn("Иван Иванов", email.subject)
        self.assertIn("завершил заполнение анкеты онбординга", email.body)

    def test_onboarding_progress_context_processor(self):
        """Verify that the onboarding_progress context processor correctly determines steps and percentages."""
        client = Client.objects.create(
            first_name="Новый",
            last_name="Клиент",
        )
        token = uuid.uuid4().hex
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hash_onboarding_token(token),
            status="created",
            expires_at=timezone.now() + timedelta(days=7)
        )

        # Test step 1: digital access
        url = reverse("clients:onboarding_digital_access", kwargs={"token": token})
        response = self.client_agent.get(url)
        self.assertEqual(response.context["onboarding_step_num"], 1)
        self.assertEqual(response.context["onboarding_step_total"], 7)
        self.assertEqual(response.context["onboarding_step_percent"], 14)

        # Test step 4: address
        url = reverse("clients:onboarding_address", kwargs={"token": token})
        response = self.client_agent.get(url)
        self.assertEqual(response.context["onboarding_step_num"], 4)
        self.assertEqual(response.context["onboarding_step_total"], 7)
        self.assertEqual(response.context["onboarding_step_percent"], 57)

    def test_onboarding_auto_save_endpoint(self):
        """Autosave stores the questionnaire draft and syncs only contact fields to Client."""
        client = Client.objects.create(
            first_name="Placeholder",
            last_name="Client",
        )
        token = uuid.uuid4().hex
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hash_onboarding_token(token),
            status="created",
            expires_at=timezone.now() + timedelta(days=7),
        )
        mos_data = MOSApplicationData.objects.get(client=client)

        auto_save_url = reverse("clients:onboarding_auto_save", kwargs={"token": token})

        response = self.client_agent.post(auto_save_url, {
            "first_name": "Konstantin",
            "last_name": "Habensky",
            "phone": "+48999888777",
            "email": "konstantin@example.com",
            "citizenship": "BY",
            "document_number": "MP1234567",
            "has_pesel": "yes",
            "street": "Mickiewicza 12",
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")

        client.refresh_from_db()
        self.assertEqual(client.first_name, "Konstantin")
        self.assertEqual(client.last_name, "Habensky")
        self.assertEqual(client.phone, "+48999888777")
        self.assertEqual(client.email, "konstantin@example.com")
        self.assertEqual(client.citizenship, "")
        self.assertIsNone(client.passport_num)

        from clients.models import ClientDigitalAccess
        da = ClientDigitalAccess.objects.get(client=client)
        self.assertTrue(da.has_pesel)

        mos_data.refresh_from_db()
        self.assertEqual(mos_data.personal_data["first_name"], "Konstantin")
        self.assertEqual(mos_data.personal_data["last_name"], "Habensky")
        self.assertEqual(mos_data.personal_data["citizenship"], "BY")
        self.assertEqual(mos_data.passport_data["document_number"], "MP1234567")
        self.assertEqual(mos_data.address_data["street"], "Mickiewicza 12")
        self.assertEqual(mos_data.status, "client_filling")

    def test_admin_review_applies_legal_fields_to_client_card(self):
        client = Client.objects.create(
            first_name="Ivan",
            last_name="Ivanov",
            phone="+48000000000",
        )
        mos_data = MOSApplicationData.objects.get(client=client)
        mos_data.personal_data = {
            "first_name": "Ivan",
            "last_name": "Ivanov",
            "phone": "+48000000000",
            "email": "ivan@example.com",
            "birth_date": "1990-05-15",
            "citizenship": "BY",
        }
        mos_data.passport_data = {"document_number": "MP1234567"}
        mos_data.status = "client_completed"
        mos_data.save()

        response = self.client_agent.post(
            reverse("clients:admin_mos_review", kwargs={"client_id": client.pk}),
            {"action": "approve"},
        )
        self.assertEqual(response.status_code, 302)

        client.refresh_from_db()
        self.assertEqual(client.email, "ivan@example.com")
        self.assertEqual(client.citizenship, "BY")
        self.assertEqual(client.passport_num, "MP1234567")
        self.assertEqual(client.birth_date.isoformat(), "1990-05-15")

        mos_data.refresh_from_db()
        self.assertEqual(mos_data.status, "mos_package_ready")

    def test_locked_onboarding_rejects_autosave(self):
        client = Client.objects.create(
            first_name="Locked",
            last_name="Client",
        )
        token = uuid.uuid4().hex
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hash_onboarding_token(token),
            status="created",
            expires_at=timezone.now() + timedelta(days=7),
        )
        mos_data = MOSApplicationData.objects.get(client=client)
        mos_data.status = "client_completed"
        mos_data.save(update_fields=["status"])

        response = self.client_agent.post(
            reverse("clients:onboarding_auto_save", kwargs={"token": token}),
            {"first_name": "Changed"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 423)
        client.refresh_from_db()
        self.assertEqual(client.first_name, "Locked")

    def test_locked_onboarding_renders_premium_lock_screen(self):
        client = Client.objects.create(
            first_name="Locked",
            last_name="Client",
        )
        token = uuid.uuid4().hex
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hash_onboarding_token(token),
            status="created",
            expires_at=timezone.now() + timedelta(days=7),
        )
        mos_data = MOSApplicationData.objects.get(client=client)
        mos_data.status = "client_completed"
        mos_data.save(update_fields=["status"])

        # GET request to step 1 (passport)
        response = self.client_agent.get(reverse("clients:onboarding_passport", kwargs={"token": token}))
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "clients/onboarding/locked.html")
        self.assertContains(response, "Редактирование недоступно", status_code=403)
        self.assertContains(response, "Анкета заполнена иностранцем", status_code=403)

        # POST request to step 1 (passport)
        response = self.client_agent.post(reverse("clients:onboarding_passport", kwargs={"token": token}), {
            "first_name": "NewName"
        })
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "clients/onboarding/locked.html")

        # Ajax request to step 1 (passport)
        response = self.client_agent.post(
            reverse("clients:onboarding_passport", kwargs={"token": token}),
            {"first_name": "NewName"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["status"], "locked")
