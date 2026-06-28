from datetime import timedelta

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from clients.models import Client, ClientOnboardingSession, Document
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

    def test_expired_token_raises_expired_exception(self):
        from clients.views.onboarding_views import OnboardingLinkExpired
        client = Client.objects.create(first_name="A", last_name="B", application_purpose="work")
        raw, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hashed,
            status="created",
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        with self.assertRaises(OnboardingLinkExpired):
            check_onboarding_session(raw)

    def test_invalid_token_returns_none(self):
        self.assertIsNone(check_onboarding_session("invalid-token-value"))

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
            "full_name": "Kowalska Anna Maria",
            "email": "test_pwd@example.com",
            "password": "supersecurepassword123",
            "password_confirm": "supersecurepassword123"
        })
        self.assertRedirects(response, reverse("clients:onboarding_start", kwargs={"token": raw}))

        # Verify user creation
        client.refresh_from_db()
        self.assertIsNotNone(client.user)
        self.assertEqual(client.first_name, "Anna Maria")
        self.assertEqual(client.last_name, "Kowalska")
        self.assertEqual(client.user.email, "test_pwd@example.com")
        self.assertEqual(client.user.first_name, "Anna Maria")
        self.assertEqual(client.user.last_name, "Kowalska")
        self.assertTrue(client.user.is_active)
        self.assertTrue(client.user.has_usable_password())
        email_address = EmailAddress.objects.get(user=client.user, email="test_pwd@example.com")
        self.assertTrue(email_address.primary)
        self.assertTrue(email_address.verified)

    def test_onboarding_set_password_requires_full_name(self):
        client = Client.objects.create(first_name="A", last_name="B", email="missing_name@example.com", application_purpose="work")
        raw, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hashed,
            status="created",
            expires_at=timezone.now() + timedelta(days=1),
        )

        with override("ru"):
            response = self.client.post(reverse("clients:onboarding_set_password", kwargs={"token": raw}), {
                "email": "missing_name@example.com",
                "password": "supersecurepassword123",
                "password_confirm": "supersecurepassword123",
            })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Пожалуйста, укажите ФИО.")
        client.refresh_from_db()
        self.assertIsNone(client.user)

    def test_onboarding_me_token_resolves_logged_in_client(self):
        User = get_user_model()
        user = User.objects.create_user(email="client_me@example.com", password="password123")
        client = Client.objects.create(first_name="A", last_name="B", email="client_me@example.com", user=user, application_purpose="work")

        # A stale staff-generated case_link session must NOT be reused for
        # self-onboarding (spec §5).
        raw, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=client,
            scope="case_link",
            token_hash=hashed,
            status="created",
            expires_at=timezone.now() + timedelta(days=1),
        )

        # Log user in
        self.client.force_login(user)

        # Try accessing with "me" token: self-onboarding resolves to a
        # client_portal session. The client has a single active case, so it is
        # auto-selected and the onboarding page renders directly (no picker).
        url = reverse("clients:onboarding_start", kwargs={"token": "me"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            ClientOnboardingSession.objects.filter(
                client=client, scope="client_portal"
            ).exists()
        )

    def test_portal_with_several_cases_still_shows_the_picker(self):
        from clients.services.cases import create_case_for_client

        User = get_user_model()
        staff = User.objects.create_user(email="staff-picker@example.com", password="x", is_staff=True)
        user = User.objects.create_user(email="client_multi@example.com", password="password123")
        client = Client.objects.create(
            first_name="Multi", last_name="Portal", email="client_multi@example.com",
            user=user, application_purpose="work",
        )
        # Second active case → a real choice exists, so the picker must appear.
        create_case_for_client(client=client, actor=staff)

        _, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=client,
            scope="client_portal",
            token_hash=hashed,
            status="active",
            expires_at=timezone.now() + timedelta(days=1),
        )

        self.client.force_login(user)
        response = self.client.get(reverse("clients:onboarding_start", kwargs={"token": "me"}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            reverse("clients:onboarding_select_case", kwargs={"token": "me"}),
        )

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
        # The client has a single active case, so "me" auto-selects it and the
        # onboarding page renders (200).
        self.assertRedirects(
            response,
            reverse("clients:onboarding_start", kwargs={"token": "me"}),
        )

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
            "full_name": "Nowak Nina",
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
        self.assertEqual(new_client.first_name, "Nina")
        self.assertEqual(new_client.last_name, "Nowak")
        self.assertEqual(user.first_name, "Nina")
        self.assertEqual(user.last_name, "Nowak")
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password("newpassword123"))
        self.assertTrue(EmailAddress.objects.get(user=user, email="returning@example.com").verified)

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

    def test_onboarding_upload_feedback_is_visible_when_file_missing(self):
        User = get_user_model()
        user = User.objects.create_user(email="upload_missing@example.com", password="password123")
        client = Client.objects.create(first_name="Upload", last_name="Missing", email="upload_missing@example.com", user=user, application_purpose="work")
        raw, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hashed,
            status="created",
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(user)

        upload_url = reverse("clients:onboarding_document_upload", kwargs={"token": raw, "doc_type": "payment_confirmation"})
        with override("ru"):
            response = self.client.post(upload_url, {}, follow=True)

        self.assertContains(response, "onboarding-messages")
        self.assertContains(response, "alert-danger")
        self.assertEqual(client.documents.count(), 0)

    def test_onboarding_upload_success_feedback_is_visible(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        User = get_user_model()
        user = User.objects.create_user(email="upload_success@example.com", password="password123")
        client = Client.objects.create(first_name="Upload", last_name="Success", email="upload_success@example.com", user=user, application_purpose="work")
        raw, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=client,
            token_hash=hashed,
            status="created",
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(user)

        upload_url = reverse("clients:onboarding_document_upload", kwargs={"token": raw, "doc_type": "payment_confirmation"})
        uploaded_file = SimpleUploadedFile("payment.pdf", self._minimal_pdf_bytes(), content_type="application/pdf")
        with override("ru"):
            response = self.client.post(upload_url, {"file": uploaded_file}, follow=True)

        self.assertContains(response, "onboarding-messages")
        self.assertContains(response, "alert-success")
        self.assertEqual(client.documents.filter(document_type="payment_confirmation").count(), 1)

    def test_onboarding_preview_cannot_open_another_clients_document(self):
        User = get_user_model()
        user = User.objects.create_user(email="preview-a@example.com", password="password123")
        client_a = Client.objects.create(
            first_name="Preview",
            last_name="Owner",
            email="preview-a@example.com",
            user=user,
            application_purpose="work",
        )
        client_b = Client.objects.create(
            first_name="Preview",
            last_name="Other",
            email="preview-b@example.com",
            application_purpose="work",
        )
        raw, hashed = generate_onboarding_token()
        ClientOnboardingSession.objects.create(
            client=client_a,
            token_hash=hashed,
            status="created",
            expires_at=timezone.now() + timedelta(days=1),
        )
        foreign_document = Document.objects.create(
            client=client_b,
            document_type="passport",
            file="documents/foreign-preview.pdf",
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("clients:onboarding_document_preview", kwargs={"token": raw, "doc_id": foreign_document.pk})
        )

        self.assertEqual(response.status_code, 404)

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

    @override_settings(LANGUAGE_CODE="ru")
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



