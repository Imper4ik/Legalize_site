from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation

from clients.models import (
    Client,
    ClientActivity,
    ClientOnboardingSession,
    Document,
    MOSApplicationData,
    Payment,
    StaffTask,
)
from clients.services.cases import create_case_for_client
from clients.services.onboarding_tokens import hash_onboarding_token
from clients.services.tasks import create_auto_task


class MultiCaseOnboardingIsolationTests(TestCase):
    def _client_with_two_cases(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(email="multi-case-client@example.test", password="secure_pwd_123")
        client = Client.objects.create(
            first_name="Multi",
            last_name="Case",
            email=user.email,
            phone="+48123456789",
            user=user,
            application_purpose="study",
            language="ru",
        )
        case_a = client.cases.get()
        case_b = create_case_for_client(client=client)
        self.client.force_login(user)
        return client, case_a, case_b

    def _case_link_session(self, client: Client, case) -> str:
        token = f"case-token-{case.pk}"
        ClientOnboardingSession.objects.create(
            client=client,
            case=case,
            token_hash=hash_onboarding_token(token),
            status="created",
            expires_at=timezone.now() + timedelta(days=7),
        )
        return token

    def test_start_page_uses_selected_case_only_for_step_documents_and_actions(self) -> None:
        client, case_a, case_b = self._client_with_two_cases()
        case_a.fingerprints_date = timezone.localdate()
        case_a.save(update_fields=["fingerprints_date"])
        MOSApplicationData.objects.update_or_create(client=client, case=case_a, defaults={"status": "fingerprints"})
        MOSApplicationData.objects.update_or_create(client=client, case=case_b, defaults={"status": "client_completed"})
        Payment.objects.create(
            client=client,
            case=case_a,
            service_description="work_service",
            total_amount=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
            status="pending",
        )
        Document.objects.create(
            client=client,
            case=case_a,
            document_type="case_a_only_document",
            file=SimpleUploadedFile("case-a.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
        )
        Document.objects.create(
            client=client,
            case=case_b,
            document_type="case_b_only_document",
            file=SimpleUploadedFile("case-b.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
        )
        token = self._case_link_session(client, case_b)

        with translation.override("ru"):
            response = self.client.get(reverse("clients:onboarding_start", kwargs={"token": token}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["case_step"], 3)
        self.assertFalse(response.context["is_post_fingerprints"])
        additional_codes = {doc["code"] for doc in response.context["additional_documents"]}
        self.assertIn("case_b_only_document", additional_codes)
        self.assertNotIn("case_a_only_document", additional_codes)

    def test_case_number_save_closes_only_matching_case_auto_task_and_logs_that_case(self) -> None:
        client, case_a, case_b = self._client_with_two_cases()
        task_a = create_auto_task(client, "case_number_missing", case=case_a)
        task_b = create_auto_task(client, "case_number_missing", case=case_b)
        assert task_a is not None
        assert task_b is not None

        case_a.authority_case_number = "WSC-II-P.6151.100.2026"
        case_a.save(update_fields=["authority_case_number"])

        task_a.refresh_from_db()
        task_b.refresh_from_db()
        self.assertEqual(task_a.status, StaffTask.STATUS_DONE)
        self.assertEqual(task_b.status, StaffTask.STATUS_OPEN)
        self.assertTrue(
            ClientActivity.objects.filter(
                client=client,
                case=case_a,
                task=task_a,
                event_type="task_completed",
            ).exists()
        )
        self.assertFalse(
            ClientActivity.objects.filter(
                client=client,
                case=case_b,
                task=task_b,
                event_type="task_completed",
            ).exists()
        )

    def test_done_client_question_is_visible_only_for_selected_case(self) -> None:
        client, case_a, case_b = self._client_with_two_cases()
        token = self._case_link_session(client, case_b)
        ask_url = reverse("clients:onboarding_ask_question", kwargs={"token": token})
        self.client.post(ask_url, {"question": "Can you check my document?"})
        task_b = StaffTask.objects.get(client=client, case=case_b, title__icontains="Вопрос от клиента")
        task_b.mark_done()
        StaffTask.objects.create(
            client=client,
            case=case_a,
            title="Вопрос от клиента: older case",
            description="Answer in another case",
            status=StaffTask.STATUS_DONE,
        )

        with translation.override("ru"):
            response = self.client.get(reverse("clients:onboarding_start", kwargs={"token": token}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Сотрудник ответил на ваш вопрос")
        self.assertEqual(
            response.context["action_items"][-1]["text"],
            "Сотрудник ответил на ваш вопрос",
        )
