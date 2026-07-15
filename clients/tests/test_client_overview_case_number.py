from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from clients.models import MOSApplicationData
from clients.testing.factories import TEST_USER_CREDENTIAL, create_test_client, create_test_user


class ClientOverviewCaseNumberTests(TestCase):
    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(purpose="work")
        self.case = self.client_obj.cases.get()
        self.case.authority_case_number = "WSC-II-P.6151.138285.2025"
        self.case.save(update_fields=["authority_case_number"])

        mos_data, _ = MOSApplicationData.objects.get_or_create(
            client=self.client_obj,
            case=self.case,
        )
        mos_data.new_residence_card_application_status = "yes"
        mos_data.new_residence_card_case_number = ""
        mos_data.save(
            update_fields=[
                "new_residence_card_application_status",
                "new_residence_card_case_number",
            ]
        )

        self.client.login(email=self.staff.email, password=TEST_USER_CREDENTIAL)

    def test_new_application_summary_uses_active_case_number(self) -> None:
        with translation.override("ru"):
            response = self.client.get(
                reverse("clients:client_detail", kwargs={"pk": self.client_obj.pk})
                + "?view=person"
            )

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("WSC-II-P.6151.138285.2025", body)
        self.assertNotIn(
            "Номер дела не указан; если были отпечатки, проверьте присоединение к делу",
            body,
        )

    def test_ajax_overview_uses_active_case_number(self) -> None:
        with translation.override("ru"):
            response = self.client.get(
                reverse("clients:client_overview_partial", kwargs={"pk": self.client_obj.pk})
            )

        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        self.assertIn("WSC-II-P.6151.138285.2025", html)
        self.assertNotIn("Номер дела не указан", html)
