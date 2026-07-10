"""A failed batch upload must leave neither DB rows nor orphaned media files.

The batch save runs in a transaction, but a DB rollback does not remove files
already written to storage. These tests exercise a mid-batch failure and assert
that the earlier file written to storage is cleaned up.
"""
from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from clients.constants import DocumentType
from clients.models import Client, Document
from clients.services.roles import ensure_predefined_roles
from clients.views import documents as documents_view

_MEDIA_ROOT = tempfile.mkdtemp(prefix="rollback-media-")


def _png_upload(name: str) -> SimpleUploadedFile:
    buffer = BytesIO()
    Image.new("RGB", (24, 24), "white").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def _media_file_count() -> int:
    return sum(1 for p in Path(_MEDIA_ROOT).rglob("*") if p.is_file())


@override_settings(MEDIA_ROOT=_MEDIA_ROOT, ASYNC_OCR_PROCESSING=True)
class BatchUploadRollbackCleanupTests(TestCase):
    def setUp(self) -> None:
        ensure_predefined_roles()
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            email="rollback-staff@example.com", password="pass", is_staff=True
        )
        self.staff.groups.add(Group.objects.get(name="Staff"))
        self.client.login(email="rollback-staff@example.com", password="pass")
        self.client_obj = Client.objects.create(
            first_name="Batch",
            last_name="Rollback",
            citizenship="PL",
            phone="+48123123123",
            email="batch-rollback@example.com",
        )
        # Clean slate for media assertions.
        for path in Path(_MEDIA_ROOT).rglob("*"):
            if path.is_file():
                path.unlink()

    def test_failure_on_second_file_leaves_no_rows_and_no_orphaned_file(self) -> None:
        real_upload = documents_view.upload_client_document
        state = {"calls": 0}

        def flaky_upload(**kwargs):
            state["calls"] += 1
            if state["calls"] == 2:
                raise RuntimeError("simulated storage/DB failure on second file")
            return real_upload(**kwargs)

        url = reverse(
            "clients:add_document",
            kwargs={
                "client_id": self.client_obj.pk,
                "doc_type": DocumentType.EMPLOYMENT_CONTRACT.value,
            },
        )

        from unittest import mock

        with mock.patch.object(documents_view, "upload_client_document", side_effect=flaky_upload):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    url,
                    data={"file": [_png_upload("first.png"), _png_upload("second.png")]},
                    HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                )

        # The first upload really wrote a file and created a row before the
        # second failed; both must be gone.
        self.assertEqual(state["calls"], 2)
        self.assertEqual(Document.objects.filter(client=self.client_obj).count(), 0)
        self.assertEqual(
            _media_file_count(),
            0,
            msg="A failed batch upload left an orphaned media file on disk",
        )

    def test_failure_after_document_saved_still_cleans_the_file(self) -> None:
        # Failure happens INSIDE upload_client_document, after the physical file
        # is written (during document.save) but before it returns — here by
        # making the activity log raise on the second document. Both files must
        # be cleaned up, not just fully-completed ones.
        from unittest import mock

        url = reverse(
            "clients:add_document",
            kwargs={
                "client_id": self.client_obj.pk,
                "doc_type": DocumentType.EMPLOYMENT_CONTRACT.value,
            },
        )
        state = {"calls": 0}
        real_log = documents_view.upload_client_document.__globals__["log_client_activity"]

        def flaky_log(*args, **kwargs):
            state["calls"] += 1
            if state["calls"] == 2:
                raise RuntimeError("activity log failed after file was written")
            return real_log(*args, **kwargs)

        with mock.patch(
            "clients.services.document_workflow.log_client_activity", side_effect=flaky_log
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    url,
                    data={"file": [_png_upload("one.png"), _png_upload("two.png")]},
                    HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                )

        self.assertEqual(Document.objects.filter(client=self.client_obj).count(), 0)
        self.assertEqual(
            _media_file_count(),
            0,
            msg="A file written before a post-save failure was left orphaned",
        )

    def test_successful_batch_persists_all_files(self) -> None:
        url = reverse(
            "clients:add_document",
            kwargs={
                "client_id": self.client_obj.pk,
                "doc_type": DocumentType.EMPLOYMENT_CONTRACT.value,
            },
        )
        response = self.client.post(
            url,
            data={"file": [_png_upload("a.png"), _png_upload("b.png")]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Document.objects.filter(client=self.client_obj).count(), 2)
        self.assertEqual(_media_file_count(), 2)
