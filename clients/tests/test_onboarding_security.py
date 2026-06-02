from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth import get_user_model
from clients.models import Client, ClientOnboardingSession
from clients.services.onboarding_tokens import generate_onboarding_token
from clients.views.onboarding_views import check_onboarding_session


class OnboardingSecurityTests(TestCase):
    def test_onboarding_session_stores_hash_not_raw(self):
        client = Client.objects.create(first_name="A", last_name="B", application_purpose="work")
        raw, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hashed,
            status="created",
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.assertFalse(ClientOnboardingSession.objects.filter(token_hash=raw).exists())
        self.assertIsNotNone(check_onboarding_session(raw))

    def test_invalid_or_expired_token_forbidden(self):
        client = Client.objects.create(first_name="A", last_name="B", application_purpose="work")
        raw, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hashed,
            status="created",
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.assertIsNone(check_onboarding_session(raw))

    def test_onboarding_redirects_to_set_password_if_no_password_set(self):
        client = Client.objects.create(first_name="A", last_name="B", email="test_no_pwd@example.com", application_purpose="work")
        raw, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hashed,
            status="created",
            expires_at=timezone.now() + timedelta(days=1),
        )
        
        # Accessing start should redirect to set-password
        url = reverse("clients:onboarding_start", kwargs={"token": raw})
        response = self.client.get(url)
        self.assertRedirects(response, reverse("clients:onboarding_set_password", kwargs={"token": raw}))

    def test_onboarding_set_password_flow(self):
        client = Client.objects.create(first_name="A", last_name="B", email="test_pwd@example.com", application_purpose="work")
        raw, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hashed,
            status="created",
            expires_at=timezone.now() + timedelta(days=1),
        )
        
        # POST to set-password
        url = reverse("clients:onboarding_set_password", kwargs={"token": raw})
        response = self.client.post(url, {
            "email": "test_pwd@example.com",
            "password": "supersecurepassword123",
            "password_confirm": "supersecurepassword123"
        })
        self.assertRedirects(response, reverse("clients:onboarding_start", kwargs={"token": raw}))
        
        # Verify user creation
        client.refresh_from_db()
        self.assertIsNotNone(client.user)
        self.assertEqual(client.user.email, "test_pwd@example.com")
        self.assertTrue(client.user.is_active)
        self.assertTrue(client.user.has_usable_password())

    def test_onboarding_me_token_resolves_logged_in_client(self):
        User = get_user_model()
        user = User.objects.create_user(email="client_me@example.com", password="password123")
        client = Client.objects.create(first_name="A", last_name="B", email="client_me@example.com", user=user, application_purpose="work")
        
        raw, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hashed,
            status="created",
            expires_at=timezone.now() + timedelta(days=1),
        )
        
        # Log user in
        self.client.force_login(user)
        
        # Try accessing with "me" token
        url = reverse("clients:onboarding_start", kwargs={"token": "me"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_dashboard_redirect_for_client_user(self):
        User = get_user_model()
        user = User.objects.create_user(email="client_redirect@example.com", password="password123")
        client = Client.objects.create(first_name="A", last_name="B", email="client_redirect@example.com", user=user, application_purpose="work")
        
        raw, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hashed,
            status="created",
            expires_at=timezone.now() + timedelta(days=1),
        )
        
        self.client.force_login(user)
        url = reverse("root_dashboard")
        response = self.client.get(url)
        self.assertRedirects(response, reverse("clients:onboarding_start", kwargs={"token": "me"}))

    def test_onboarding_returning_client_reuse_user(self):
        # 1. Old archived client with user
        User = get_user_model()
        user = User.objects.create_user(email="returning@example.com", password="oldpassword123")
        old_client = Client.objects.create(
            first_name="Old",
            last_name="Archived",
            email="returning@example.com",
            user=user,
            archived_at=timezone.now()
        )
        
        # 2. New client
        new_client = Client.objects.create(
            first_name="New",
            last_name="Active",
            email="returning@example.com",
            application_purpose="work"
        )
        raw, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=new_client,
            token_hash=hashed,
            status="created",
            expires_at=timezone.now() + timedelta(days=1),
        )
        
        # Accessing set-password for new client
        url = reverse("clients:onboarding_set_password", kwargs={"token": raw})
        response = self.client.post(url, {
            "email": "returning@example.com",
            "password": "newpassword123",
            "password_confirm": "newpassword123"
        })
        self.assertRedirects(response, reverse("clients:onboarding_start", kwargs={"token": raw}))
        
        # Refresh and assert
        old_client = Client.all_objects.get(pk=old_client.pk)
        new_client.refresh_from_db()
        user.refresh_from_db()
        self.assertIsNone(old_client.user)
        self.assertEqual(new_client.user, user)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password("newpassword123"))

    def _minimal_pdf_bytes(self):
        return (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
            b"xref\n0 4\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000058 00000 n \n"
            b"0000000115 00000 n \n"
            b"trailer<</Size 4/Root 1 0 R>>\n"
            b"startxref\n183\n"
            b"%%EOF\n"
        )

    def test_onboarding_actions_log_activity_with_actor(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from clients.models import ClientActivity
        
        User = get_user_model()
        user = User.objects.create_user(email="logger@example.com", password="password123")
        client = Client.objects.create(first_name="Log", last_name="Actor", email="logger@example.com", user=user, application_purpose="work")
        
        raw, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hashed,
            status="created",
            expires_at=timezone.now() + timedelta(days=1),
        )
        
        self.client.force_login(user)
        
        # 1. Upload document
        upload_url = reverse("clients:onboarding_document_upload", kwargs={"token": raw, "doc_type": "address_proof"})
        uploaded_file = SimpleUploadedFile("contract.pdf", self._minimal_pdf_bytes(), content_type="application/pdf")
        
        response = self.client.post(upload_url, {"file": uploaded_file})
        self.assertEqual(response.status_code, 302)
        
        # Verify activity log
        activity_upload = ClientActivity.objects.filter(client=client, event_type="document_uploaded").first()
        self.assertIsNotNone(activity_upload)
        self.assertEqual(activity_upload.actor, user)
        
        # 2. Delete document
        document = activity_upload.document
        self.assertIsNotNone(document)
        delete_url = reverse("clients:onboarding_document_delete", kwargs={"token": raw, "doc_id": document.id})
        
        response = self.client.post(delete_url)
        self.assertEqual(response.status_code, 302)
        
        # Verify activity log
        activity_delete = ClientActivity.objects.filter(client=client, event_type="document_deleted").first()
        self.assertIsNotNone(activity_delete)
        self.assertEqual(activity_delete.actor, user)

    def test_failed_email_health_alert(self):
        from clients.models.email import EmailLog
        client = Client.objects.create(first_name="Alert", last_name="Email", email="alert@example.com", application_purpose="work")
        
        # Initially no alerts for failed emails
        self.assertFalse(any(a["title"] == "Ошибка отправки писем клиенту" for a in client.get_health_alerts()))
        
        # Create a failed email log
        EmailLog.objects.create(
            client=client,
            subject="Test Subject",
            body="Test Body",
            recipients="alert@example.com",
            delivery_status="failed"
        )
        
        # Should now have the danger health alert
        alerts = client.get_health_alerts()
        failed_alert = next((a for a in alerts if a["title"] == "Ошибка отправки писем клиенту"), None)
        self.assertIsNotNone(failed_alert)
        self.assertEqual(failed_alert["level"], "danger")
        self.assertIn("Не удалось отправить писем клиенту", failed_alert["message"])



