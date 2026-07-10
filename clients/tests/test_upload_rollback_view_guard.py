"""HTTP regression coverage for safe upload rollback cleanup."""
from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from clients.constants import DocumentType
from clients.models import Client, Document
from clients.services.roles import ensure_predefined_roles

_MEDIA_ROOT = tempfile.mkdtemp(prefix="rollback-view-guard-")


def _png_upload(name: str) -> SimpleUploadedFile:
    buffer = BytesIO()
    Image.new("RGB", (24, 24), "white").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=_MEDIA_ROOT, ASYNC_OCR_PROCESSING=True)
class UploadRollbackViewGuardTests(TestCase):
    def setUp(self) -> None:
        ensure_predefined_roles()
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            email="rollback-view-guard@example.test",
            password="pass",
            is_staff=True,
        )
        self.staff.groups.add(Group.objects.get(name="Staff"))
        self.client.login(email="rollback-view-guard@example.test", password="pass")
        self.client_obj = Client.objects.create(
            first_name="Rollback",
            last_name="Guard",
            citizenship="PL",
            phone="+48123123125",
            email="rollback-view-guard-client@example.test",
        )
        for path in Path(_MEDIA_ROOT).rglob("*"):
            if path.is_file():
                path.unlink()

    def tearDown(self) -> None:
        for path in sorted(Path(_MEDIA_ROOT).rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        super().tearDown()

    def test_early_save_failure_does_not_delete_existing_uncommitted_name(self) -> None:
        storage = Document._meta.get_field("file").storage
        existing_name = "early-failure.png"
        storage.save(existing_name, ContentFile(b"existing file"))

        url = reverse(
            "clients:add_document",
            kwargs={
                "client_id": self.client_obj.pk,
                "doc_type": DocumentType.EMPLOYMENT_CONTRACT.value,
            },
        )

        with mock.patch.object(Document, "save", side_effect=RuntimeError("early save failure")):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    url,
                    data={"file": _png_upload(existing_name)},
                    HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                )

        self.assertEqual(Document.objects.filter(client=self.client_obj).count(), 0)
        self.assertTrue(storage.exists(existing_name))
        with storage.open(existing_name, "rb") as stored_file:
            self.assertEqual(stored_file.read(), b"existing file")
