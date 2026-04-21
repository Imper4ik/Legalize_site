from __future__ import annotations

from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from PIL import Image

from clients.validators import validate_uploaded_document


def build_image_upload(name: str, *, size=(20, 20), image_format="PNG", content_type="image/png"):
    buffer = BytesIO()
    image = Image.new("RGB", size, "white")
    image.save(buffer, format=image_format)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)


class UploadedDocumentValidatorTests(SimpleTestCase):
    def test_rejects_filename_with_path_components(self):
        uploaded = build_image_upload("..\\secret.png")

        with self.assertRaises(ValidationError):
            validate_uploaded_document(uploaded)

    @override_settings(MAX_IMAGE_PIXELS=100)
    def test_rejects_image_above_pixel_limit(self):
        uploaded = build_image_upload("large.png", size=(11, 10))

        with self.assertRaises(ValidationError):
            validate_uploaded_document(uploaded)
