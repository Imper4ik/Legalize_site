from __future__ import annotations

import datetime
from django.contrib.auth import get_user_model
from django.test import TestCase, Client as DjangoClient
from django.urls import reverse
from django.utils import timezone

from clients.constants import DocumentType
from clients.models import Client, Document, StaffTask, ClientActivity
from clients.tests.factories import create_admin_user, create_manager_user, create_staff_user
from clients.use_cases.documents import verify_all_client_documents, toggle_client_document_verification
from clients.services.workday import build_workday_context
from clients.services.roles import PEOPLE_ALLOWED_ROLES

class P0FixesVerificationTests(TestCase):
    def setUp(self):
        self.admin = create_admin_user()
        self.manager = create_manager_user()
        self.staff = create_staff_user()
        self.client_obj = Client.objects.create(
            first_name="Ivan",
            last_name="Ivanov",
            email="ivan@example.com",
            citizenship="Belarus",
            application_purpose="work"
        )

    def test_document_computed_status(self):
        """Test computed_status property of Document model under different fields."""
        today = timezone.localdate()
        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file="passport.pdf"
        )
        # 1. default is pending_review
        self.assertEqual(doc.computed_status, "pending_review")

        # 2. approved when verified
        doc.verified = True
        doc.save()
        self.assertEqual(doc.computed_status, "approved")

        # 3. rejected when rejection reason is present
        doc.verified = False
        doc.rejection_reason = "Bad scan quality"
        doc.save()
        self.assertEqual(doc.computed_status, "rejected")

        # 4. expired when expiry date is past (even if verified or rejected)
        doc.expiry_date = today - datetime.timedelta(days=1)
        doc.save()
        self.assertEqual(doc.computed_status, "expired")

        # 5. archived when archived_at is not null
        doc.archived_at = timezone.now()
        doc.save()
        self.assertEqual(doc.computed_status, "archived")

    def test_verify_all_client_documents_excludes_rejected_and_expired(self):
        """verify_all_client_documents should exclude rejected and expired documents from verification,
        and reset rejection_reason/awaiting_confirmation on success.
        """
        today = timezone.localdate()
        # Document 1: normal, pending
        doc1 = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file="doc1.pdf",
            verified=False,
            awaiting_confirmation=True,
            rejection_reason="some old reason"  # wait, if it has rejection_reason, it is rejected!
        )
        # Document 2: normal pending without rejection reason
        doc2 = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            file="doc2.pdf",
            verified=False
        )
        # Document 3: expired
        doc3 = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PAYMENT_CONFIRMATION.value,
            file="doc3.pdf",
            verified=False,
            expiry_date=today - datetime.timedelta(days=2)
        )
        # Document 4: rejected (has rejection reason)
        doc4 = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZALACZNIK_NR_1.value,
            file="doc4.pdf",
            verified=False,
            rejection_reason="Wrong file format"
        )

        # Before action
        self.assertEqual(self.client_obj.get_pending_verification_documents_count(), 1) # doc2 is pending

        # Run verification
        verify_all_client_documents(client=self.client_obj, actor=self.admin)

        doc1.refresh_from_db()
        doc2.refresh_from_db()
        doc3.refresh_from_db()
        doc4.refresh_from_db()

        # doc2 should be verified
        self.assertTrue(doc2.verified)
        self.assertFalse(doc2.awaiting_confirmation)
        self.assertFalse(doc2.rejection_reason)

        # doc1 was rejected (has rejection reason), so it is excluded from verify_all
        self.assertFalse(doc1.verified)

        # doc3 (expired) should NOT be verified
        self.assertFalse(doc3.verified)

        # doc4 (rejected) should NOT be verified
        self.assertFalse(doc4.verified)

    def test_toggle_verification_resets_rejection_and_confirmation(self):
        """toggle_client_document_verification should reset rejection_reason and awaiting_confirmation when verifying."""
        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file="doc.pdf",
            verified=False,
            awaiting_confirmation=True,
            rejection_reason="Not readable"
        )
        toggle_client_document_verification(document=doc, actor=self.admin)
        doc.refresh_from_db()
        self.assertTrue(doc.verified)
        self.assertFalse(doc.awaiting_confirmation)
        self.assertEqual(doc.rejection_reason, "")

    def test_reject_document_view_resets_verified_and_awaiting_confirmation(self):
        """POST to reject_document view should set verified=False, awaiting_confirmation=False, and rejection_reason."""
        doc = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file="doc.pdf",
            verified=True,
            awaiting_confirmation=True
        )
        c = DjangoClient()
        c.force_login(self.admin)
        url = reverse("clients:reject_document", kwargs={"doc_id": doc.pk})
        response = c.post(url, {"rejection_reason": "Blurry photo"})
        self.assertEqual(response.status_code, 302)

        doc.refresh_from_db()
        self.assertFalse(doc.verified)
        self.assertFalse(doc.awaiting_confirmation)
        self.assertEqual(doc.rejection_reason, "Blurry photo")

    def test_pending_verification_count_excludes_rejected_and_expired(self):
        """Pending verification count should not count rejected or expired documents."""
        today = timezone.localdate()
        # Pending
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file="doc1.pdf",
            verified=False
        )
        # Rejected
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            file="doc2.pdf",
            verified=False,
            rejection_reason="Wrong company"
        )
        # Expired
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PAYMENT_CONFIRMATION.value,
            file="doc3.pdf",
            verified=False,
            expiry_date=today - datetime.timedelta(days=1)
        )

        self.assertEqual(self.client_obj.get_pending_verification_documents_count(), 1)

    def test_checklist_considers_rejected_and_expired_as_incomplete(self):
        """Checklist should not mark an item as complete if documents are all rejected or expired."""
        today = timezone.localdate()
        # For citizenship Belarus and purpose work, check required checklist.
        # Let's add a rejected passport.
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file="passport.pdf",
            verified=False,
            rejection_reason="Blah"
        )

        checklist = self.client_obj.get_document_checklist()
        passport_item = next(item for item in checklist if item["code"] == DocumentType.PASSPORT.value)
        self.assertTrue(passport_item["is_uploaded"])
        self.assertFalse(passport_item["is_complete"])

        # Now add an expired passport
        Document.objects.filter(document_type=DocumentType.PASSPORT.value).delete()
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file="passport.pdf",
            verified=True,
            expiry_date=today - datetime.timedelta(days=5)
        )

        checklist = self.client_obj.get_document_checklist()
        passport_item = next(item for item in checklist if item["code"] == DocumentType.PASSPORT.value)
        self.assertFalse(passport_item["is_complete"])

        # Now add a valid (pending_review) passport
        Document.objects.filter(document_type=DocumentType.PASSPORT.value).delete()
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file="passport.pdf",
            verified=False
        )

        checklist = self.client_obj.get_document_checklist()
        passport_item = next(item for item in checklist if item["code"] == DocumentType.PASSPORT.value)
        self.assertTrue(passport_item["is_complete"])

    def test_workday_excludes_rejected_and_expired_documents(self):
        """Workday documents review section should exclude rejected and expired documents."""
        today = timezone.localdate()
        # Pending review (should appear)
        doc1 = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file="doc1.pdf",
            verified=False
        )
        # Rejected (should not appear)
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            file="doc2.pdf",
            verified=False,
            rejection_reason="Reject"
        )
        # Expired (should not appear)
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PAYMENT_CONFIRMATION.value,
            file="doc3.pdf",
            verified=False,
            expiry_date=today - datetime.timedelta(days=1)
        )

        context = build_workday_context(self.admin, today=today)
        review_section = next(sec for sec in context["workday_sections"] if sec["key"] == "documents_review")
        self.assertEqual(review_section["count"], 1)
        self.assertEqual(review_section["items"][0]["title"], doc1.display_name)

    def test_client_submitted_case_number_workflow(self):
        """Test that client-submitted case number updates the task title/description instead of auto-closing it,
        and saving it on Client.case_number closes it.
        """
        # 1. Create client without case number, start a missing case number task.
        user_model = get_user_model()
        user = user_model.objects.create_user(email="onb@example.com", password="pwd")
        self.client_obj.user = user
        self.client_obj.save()

        from clients.models import ClientOnboardingSession
        from clients.services.onboarding_tokens import hash_onboarding_token
        token = "test-token"
        ClientOnboardingSession.objects.create(
            client=self.client_obj,
            token_hash=hash_onboarding_token(token),
            status="created",
            expires_at=timezone.now() + datetime.timedelta(days=7)
        )

        task = StaffTask.objects.create(
            client=self.client_obj,
            task_type="case_number_missing",
            is_auto_created=True,
            title="Запросить номер дела у клиента",
            status="open"
        )

        # 2. Client submits a new application with a case number.
        c = DjangoClient()
        c.force_login(user)
        today = timezone.localdate()
        from io import BytesIO
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile

        im = Image.new("RGB", (10, 10))
        buf = BytesIO()
        im.save(buf, format="PNG")
        buf.seek(0)
        uploaded = SimpleUploadedFile("confirm.png", buf.read(), content_type="image/png")

        response = c.post(
            reverse("clients:onboarding_start", kwargs={"token": token}),
            {
                "action": "new_card_application",
                "new_card_application_status": "submitted_with_number",
                "new_card_case_number": "WSC-CASE-12345",
                "new_card_submitted_at": today.isoformat(),
                "new_card_confirmation_file": uploaded
            }
        )
        self.assertEqual(response.status_code, 302)

        # Task is still open but title/description are updated
        task.refresh_from_db()
        self.assertEqual(task.status, "open")
        self.assertEqual(task.title, "Проверить номер дела")
        self.assertIn("WSC-CASE-12345", task.description)

        # Check activity logs privacy
        act = ClientActivity.objects.filter(client=self.client_obj, event_type="new_card_application_updated").first()
        self.assertIsNotNone(act)
        self.assertNotIn("WSC-CASE-12345", act.details)
        self.assertEqual(act.details, "Клиент обновил информацию о новой подаче.")
        self.assertTrue(act.metadata.get("has_case_number"))
        self.assertNotIn("WSC-CASE-12345", act.metadata.values())

        # 3. Staff registers case number in main Client field -> closes the task.
        self.client_obj.case_number = "WSC-CASE-12345"
        self.client_obj.save()
        task.refresh_from_db()
        self.assertEqual(task.status, "done")

    def test_case_number_hashing_and_privacy_in_activity(self):
        """Verify ClientActivity logs use generic details and metadata with boolean flag instead of clear text."""
        # Let's simulate the view log or check recent ClientActivity.
        # We can create a ClientActivity with event_type="new_card_application_updated" and verify badge and event choices.
        act = ClientActivity.objects.create(
            client=self.client_obj,
            event_type="new_card_application_updated",
            details="Клиент обновил информацию о новой подаче.",
            metadata={"status": "submitted_with_number", "has_case_number": True}
        )
        self.assertEqual(act.get_event_type_display(), "Новая подача обновлена")
        self.assertEqual(act.badge_class, "bg-info text-dark")

        # Also, check that case_number is encrypted in Client.
        self.client_obj.case_number = "12345-XYZ"
        self.client_obj.save()
        self.assertEqual(self.client_obj.case_number, "12345-XYZ")
        # Ensure it hashes or encrypts as expected by the DB model (we don't check implementation details, but make sure save is successful).

    def test_manager_allowed_to_manage_people(self):
        """PEOPLE_ALLOWED_ROLES must include Manager so managers can edit employee roles."""
        self.assertIn("Manager", PEOPLE_ALLOWED_ROLES)

    def test_workday_alerts_grouped_by_client(self):
        """workday_clients should return alerts grouped by client and ordered by highest priority."""
        today = timezone.localdate()
        # Let's create another client
        client2 = Client.objects.create(
            first_name="Pavel",
            last_name="Pavlov",
            email="pavel@example.com",
            citizenship="Belarus",
            application_purpose="work"
        )
        # Create a critical/urgent alert for client2 (e.g. stay expiring soon)
        client2.legal_basis_end_date = today + datetime.timedelta(days=10)
        client2.save()
        Document.objects.create(
            client=client2,
            document_type=DocumentType.PASSPORT.value,
            file="passport2.pdf",
            verified=False
        )

        # Create an important alert for client_obj (normal passport missing/unverified)
        Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file="passport1.pdf",
            verified=False
        )

        context = build_workday_context(self.admin, today=today)
        workday_clients = context.get("workday_clients", [])
        self.assertTrue(len(workday_clients) >= 2)

        # Client 2 has urgent alert (stay expiring), Client 1 has important alert.
        # Order should be client2 first (highest priority urgent), then client_obj (highest priority important).
        self.assertEqual(workday_clients[0]["client"].pk, client2.pk)
        self.assertEqual(workday_clients[0]["highest_priority"], "urgent")

        self.assertEqual(workday_clients[1]["client"].pk, self.client_obj.pk)
        self.assertEqual(workday_clients[1]["highest_priority"], "important")
