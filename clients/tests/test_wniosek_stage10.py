from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from clients.constants import DocumentType
from clients.models import AppSettings, Client, WniosekAttachment, WniosekSubmission
from clients.services.notifications import _get_missing_documents_context


class WniosekFlowStage10Tests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            email="staff_wniosek@example.com",
            password="pass",
            is_staff=True,
        )
        self.client.login(email="staff_wniosek@example.com", password="pass")
        self.client_obj = Client.objects.create(
            first_name="Maria",
            last_name="Kowalska",
            citizenship="PL",
            phone="+48111111222",
            email="maria-wniosek@example.com",
            application_purpose="work",
            language="pl",
        )

    def test_confirm_mazowiecki_print_records_submission_and_matches_known_documents(self):
        passport_label = str(self.client_obj.get_document_name_by_code(DocumentType.PASSPORT.value))
        custom_label = "Pelna teczka klienta"

        response = self.client.post(
            reverse(
                "clients:client_document_print_confirm",
                kwargs={"pk": self.client_obj.pk, "doc_type": "mazowiecki_application"},
            ),
            data={"attachments": [passport_label, custom_label, passport_label]},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("auto_print=1", response.url)

        submission = WniosekSubmission.objects.get(client=self.client_obj)
        self.assertEqual(submission.document_kind, WniosekSubmission.DocumentKind.MAZOWIECKI_APPLICATION)
        self.assertEqual(submission.attachment_count, 2)
        self.assertEqual(submission.confirmed_by, self.staff)

        attachments = list(
            WniosekAttachment.objects.filter(submission=submission).order_by("position")
        )
        self.assertEqual([item.entered_name for item in attachments], [passport_label, custom_label])
        self.assertEqual(attachments[0].document_type, DocumentType.PASSPORT.value)
        self.assertEqual(attachments[1].document_type, "")

    def test_confirm_mazowiecki_matches_attachment_without_polish_diacritics(self):
        response = self.client.post(
            reverse(
                "clients:client_document_print_confirm",
                kwargs={"pk": self.client_obj.pk, "doc_type": "mazowiecki_application"},
            ),
            data={"attachments": ["zalacznik nr 1"]},
        )

        self.assertEqual(response.status_code, 302)
        attachment = WniosekAttachment.objects.get(submission__client=self.client_obj)
        self.assertEqual(attachment.document_type, DocumentType.ZALACZNIK_NR_1.value)

    def test_confirm_mazowiecki_matches_short_existing_checklist_label(self):
        response = self.client.post(
            reverse(
                "clients:client_document_print_confirm",
                kwargs={"pk": self.client_obj.pk, "doc_type": "mazowiecki_application"},
            ),
            data={"attachments": ["zus rca"]},
        )

        self.assertEqual(response.status_code, 302)
        attachment = WniosekAttachment.objects.get(submission__client=self.client_obj)
        self.assertEqual(attachment.document_type, DocumentType.ZUS_RCA_OR_INSURANCE.value)

    def test_confirm_mazowiecki_matches_common_tax_alias(self):
        response = self.client.post(
            reverse(
                "clients:client_document_print_confirm",
                kwargs={"pk": self.client_obj.pk, "doc_type": "mazowiecki_application"},
            ),
            data={"attachments": ["cit 8"]},
        )

        self.assertEqual(response.status_code, 302)
        attachment = WniosekAttachment.objects.get(submission__client=self.client_obj)
        self.assertEqual(attachment.document_type, DocumentType.EMPLOYER_TAX_RETURN.value)

    def test_confirm_mazowiecki_preserves_custom_office_and_proxy_lines(self):
        response = self.client.post(
            reverse(
                "clients:client_document_print_confirm",
                kwargs={"pk": self.client_obj.pk, "doc_type": "mazowiecki_application"},
            ),
            data={
                "attachments": ["cit 8"],
                "office_line": ["Inny urząd", "", "Testowa 1", ""],
                "proxy_line": ["Jan Kowalski", "", "", ""],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("office_line=Inny+urz%C4%85d", response.url)
        self.assertIn("office_line=", response.url)
        self.assertIn("proxy_line=Jan+Kowalski", response.url)

    def test_mazowiecki_print_uses_global_templates_by_default(self):
        app_settings = AppSettings.get_solo()
        app_settings.mazowiecki_office_template = "Urzad testowy\nW Warszawie alternatywnie"
        app_settings.mazowiecki_proxy_template = "Anna Nowak\nPelnomocnik"
        app_settings.save()

        response = self.client.get(
            reverse(
                "clients:client_document_print",
                kwargs={"pk": self.client_obj.pk, "doc_type": "mazowiecki_application"},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Urzad testowy"')
        self.assertContains(response, 'value="W Warszawie alternatywnie"')
        self.assertContains(response, 'value="Anna Nowak"')
        self.assertContains(response, 'value="Pelnomocnik"')

    def test_mazowiecki_print_allows_saved_blank_global_templates(self):
        app_settings = AppSettings.get_solo()
        app_settings.mazowiecki_office_template = ""
        app_settings.mazowiecki_proxy_template = ""
        app_settings.save()

        response = self.client.get(
            reverse(
                "clients:client_document_print",
                kwargs={"pk": self.client_obj.pk, "doc_type": "mazowiecki_application"},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'value="Mazowiecki Urząd Wojewódzki"')
        self.assertNotContains(response, 'value="Pełnomocnik"')

    def test_checklist_marks_wniosek_submissions_and_keeps_custom_rows(self):
        passport_label = str(self.client_obj.get_document_name_by_code(DocumentType.PASSPORT.value))
        self.client.post(
            reverse(
                "clients:client_document_print_confirm",
                kwargs={"pk": self.client_obj.pk, "doc_type": "mazowiecki_application"},
            ),
            data={"attachments": [passport_label, "Umowa od klienta"]},
        )

        checklist = self.client_obj.get_document_checklist()
        passport_item = next(item for item in checklist if item["code"] == DocumentType.PASSPORT.value)
        self.assertFalse(passport_item["is_uploaded"])
        self.assertTrue(passport_item["is_submitted"])
        self.assertTrue(passport_item["is_complete"])
        self.assertEqual(len(passport_item["submitted_records"]), 1)

        custom_item = next(item for item in checklist if item.get("is_custom_submission"))
        self.assertEqual(custom_item["name"], "Umowa od klienta")
        self.assertTrue(custom_item["is_complete"])

    def test_existing_blank_attachment_is_mapped_back_to_known_checklist_item(self):
        submission = WniosekSubmission.objects.create(
            client=self.client_obj,
            document_kind=WniosekSubmission.DocumentKind.MAZOWIECKI_APPLICATION,
            attachment_count=1,
            confirmed_by=self.staff,
        )
        WniosekAttachment.objects.create(
            submission=submission,
            document_type="",
            entered_name="zalacznik nr 1",
            position=0,
        )

        checklist = self.client_obj.get_document_checklist()
        zalacznik_item = next(item for item in checklist if item["code"] == DocumentType.ZALACZNIK_NR_1.value)
        self.assertTrue(zalacznik_item["is_submitted"])
        self.assertFalse(any(item.get("is_custom_submission") for item in checklist))

    def test_existing_blank_short_alias_is_mapped_back_without_duplicate_custom_row(self):
        submission = WniosekSubmission.objects.create(
            client=self.client_obj,
            document_kind=WniosekSubmission.DocumentKind.MAZOWIECKI_APPLICATION,
            attachment_count=1,
            confirmed_by=self.staff,
        )
        WniosekAttachment.objects.create(
            submission=submission,
            document_type="",
            entered_name="zus rca",
            position=0,
        )

        checklist = self.client_obj.get_document_checklist()
        zus_item = next(item for item in checklist if item["code"] == DocumentType.ZUS_RCA_OR_INSURANCE.value)
        self.assertTrue(zus_item["is_submitted"])
        self.assertFalse(any(item.get("is_custom_submission") for item in checklist))

    def test_missing_documents_context_excludes_documents_marked_submitted_via_wniosek(self):
        passport_label = str(self.client_obj.get_document_name_by_code(DocumentType.PASSPORT.value))
        self.client.post(
            reverse(
                "clients:client_document_print_confirm",
                kwargs={"pk": self.client_obj.pk, "doc_type": "mazowiecki_application"},
            ),
            data={"attachments": [passport_label]},
        )

        context = _get_missing_documents_context(self.client_obj, "pl")
        missing_names = [item["name"] for item in context["documents"]]

        self.assertNotIn(passport_label, missing_names)
        self.assertGreater(len(missing_names), 0)

    def test_delete_wniosek_attachment_removes_single_mark_and_updates_count(self):
        passport_label = str(self.client_obj.get_document_name_by_code(DocumentType.PASSPORT.value))
        self.client.post(
            reverse(
                "clients:client_document_print_confirm",
                kwargs={"pk": self.client_obj.pk, "doc_type": "mazowiecki_application"},
            ),
            data={"attachments": [passport_label, "Umowa od klienta"]},
        )

        submission = WniosekSubmission.objects.get(client=self.client_obj)
        custom_attachment = WniosekAttachment.objects.get(
            submission=submission,
            document_type="",
        )

        response = self.client.post(
            reverse(
                "clients:wniosek_attachment_delete",
                kwargs={"attachment_id": custom_attachment.pk},
            ),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")

        submission.refresh_from_db()
        self.assertEqual(submission.attachment_count, 1)
        self.assertFalse(WniosekAttachment.objects.filter(pk=custom_attachment.pk).exists())
        self.assertTrue(
            WniosekAttachment.objects.filter(
                submission=submission,
                document_type=DocumentType.PASSPORT.value,
            ).exists()
        )

    def test_delete_last_wniosek_attachment_removes_empty_submission(self):
        passport_label = str(self.client_obj.get_document_name_by_code(DocumentType.PASSPORT.value))
        self.client.post(
            reverse(
                "clients:client_document_print_confirm",
                kwargs={"pk": self.client_obj.pk, "doc_type": "mazowiecki_application"},
            ),
            data={"attachments": [passport_label]},
        )

        attachment = WniosekAttachment.objects.get(submission__client=self.client_obj)
        submission_id = attachment.submission_id

        response = self.client.post(
            reverse(
                "clients:wniosek_attachment_delete",
                kwargs={"attachment_id": attachment.pk},
            ),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertFalse(WniosekAttachment.objects.filter(pk=attachment.pk).exists())
        self.assertFalse(WniosekSubmission.objects.filter(pk=submission_id).exists())
