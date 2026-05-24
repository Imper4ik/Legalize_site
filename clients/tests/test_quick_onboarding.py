import uuid
from datetime import timedelta
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from django.core import mail

from clients.models import Client, ClientOnboardingSession, MOSApplicationData
from clients.forms import ClientForm
from clients.views.onboarding_views import quick_create_client_onboarding
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
        self.assertIn(session.token_hash, data["link"])

    def test_onboarding_step1_syncs_with_client_model(self):
        """Verify that when a client saves Step 1 of onboarding, the Client model is updated in real-time."""
        # Create a client placeholder
        client = Client.objects.create(
            first_name="Новый",
            last_name="Клиент",
            assigned_staff=self.manager,
            language="pl",
        )
        token = uuid.uuid4().hex
        session = ClientOnboardingSession.objects.create(
            client=client,
            token_hash=token,
            status="created",
            expires_at=timezone.now() + timedelta(days=7)
        )

        step1_url = reverse("clients:onboarding_passport", kwargs={"token": token})
        
        # Post real client details
        response = self.client_agent.post(step1_url, {
            "first_name": "Иван",
            "last_name": "Иванов",
            "birth_date": "1990-05-15",
            "citizenship": "BY",
            "document_number": "MP1234567",
            "expiry_date": "2030-05-15",
        })
        self.assertEqual(response.status_code, 302) # Redirects to next step

        # Refresh client and check synced fields
        client.refresh_from_db()
        self.assertEqual(client.first_name, "Иван")
        self.assertEqual(client.last_name, "Иванов")
        self.assertEqual(client.citizenship, "BY")
        self.assertEqual(client.passport_num, "MP1234567")
        self.assertEqual(client.birth_date.isoformat(), "1990-05-15")

    def test_onboarding_completion_notifies_staff(self):
        """Verify that completing onboarding sends an email notification to the assigned staff."""
        client = Client.objects.create(
            first_name="Иван",
            last_name="Иванов",
            assigned_staff=self.manager,
            language="pl",
        )
        token = uuid.uuid4().hex
        session = ClientOnboardingSession.objects.create(
            client=client,
            token_hash=token,
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
        })
        self.assertEqual(response.status_code, 302) # Redirect to review
        
        # Verify status
        mos_data.refresh_from_db()
        self.assertEqual(mos_data.status, "client_completed")

        # Verify email was sent to self.manager
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn(self.manager.email, email.to)
        self.assertIn("Иван Иванов", email.subject)
        self.assertIn("завершил заполнение анкеты онбординга", email.body)
