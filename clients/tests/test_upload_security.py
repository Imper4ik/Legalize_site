from __future__ import annotations

from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from clients.validators import validate_uploaded_document


VALID_MINIMAL_PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"


class DummyUpload(BytesIO):
    def __init__(self, name: str, payload: bytes, content_type: str):
        super().__init__(payload)
        self.name = name
        self.content_type = content_type
        self.size = len(payload)


class UploadSecurityTests(SimpleTestCase):
    def test_fake_pdf_extension_is_rejected(self):
        fake_pdf = SimpleUploadedFile("fake.pdf", b"not a pdf", content_type="application/pdf")
        with self.assertRaises(ValidationError):
            validate_uploaded_document(fake_pdf)

    def test_corrupted_pdf_is_rejected(self):
        corrupted = SimpleUploadedFile("corrupt.pdf", b"%PDF-1.4\n%%%%broken", content_type="application/pdf")
        with self.assertRaises(ValidationError):
            validate_uploaded_document(corrupted)

    def test_encrypted_pdf_is_rejected(self):
        encrypted_like = SimpleUploadedFile(
            "encrypted.pdf",
            b"%PDF-1.7\n1 0 obj\n<< /Encrypt 2 0 R >>\nendobj\n%%EOF",
            content_type="application/pdf",
        )
        with self.assertRaises(ValidationError):
            validate_uploaded_document(encrypted_like)

    @override_settings(MAX_UPLOAD_SIZE_MB=1)
    def test_oversized_file_is_rejected(self):
        oversized = SimpleUploadedFile("large.pdf", VALID_MINIMAL_PDF + b"a" * (1024 * 1024), content_type="application/pdf")
        with self.assertRaises(ValidationError):
            validate_uploaded_document(oversized)

    def test_path_traversal_filename_is_rejected(self):
        upload = DummyUpload("../secret.pdf", VALID_MINIMAL_PDF, "application/pdf")
        with self.assertRaises(ValidationError):
            validate_uploaded_document(upload)
