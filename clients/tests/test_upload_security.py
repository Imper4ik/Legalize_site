from __future__ import annotations

from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from PIL import Image
from pypdf import PdfWriter

from clients.validators import validate_uploaded_document


def _build_valid_pdf() -> bytes:
    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(buffer)
    return buffer.getvalue()


VALID_MINIMAL_PDF = _build_valid_pdf()


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

    def test_filename_with_backslash_is_rejected(self):
        upload = DummyUpload("..\\secret.pdf", VALID_MINIMAL_PDF, "application/pdf")
        with self.assertRaises(ValidationError):
            validate_uploaded_document(upload)

    def test_empty_file_is_rejected(self):
        upload = DummyUpload("empty.pdf", b"", "application/pdf")
        with self.assertRaises(ValidationError):
            validate_uploaded_document(upload)

    def test_wrong_mime_type_is_rejected(self):
        upload = DummyUpload("doc.pdf", VALID_MINIMAL_PDF, "text/plain")
        with self.assertRaises(ValidationError):
            validate_uploaded_document(upload)

    @override_settings(MAX_IMAGE_PIXELS=100)
    def test_huge_image_is_rejected(self):
        image = Image.new("RGB", (11, 10), "white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        upload = SimpleUploadedFile("huge.png", buffer.getvalue(), content_type="image/png")
        with self.assertRaises(ValidationError):
            validate_uploaded_document(upload)

    def test_valid_pdf_is_accepted(self):
        upload = DummyUpload("ok.pdf", VALID_MINIMAL_PDF, "application/pdf")
        self.assertIs(validate_uploaded_document(upload), upload)
        self.assertEqual(upload.tell(), 0)

    def test_valid_image_is_accepted(self):
        image = Image.new("RGB", (20, 20), "white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        upload = SimpleUploadedFile("ok.png", buffer.getvalue(), content_type="image/png")
        returned = validate_uploaded_document(upload)
        self.assertIs(returned, upload)
