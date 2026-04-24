from __future__ import annotations

from importlib import import_module
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

FILE_INPUT_ACCEPT = ".pdf,.jpg,.jpeg,.png,.webp"

ALLOWED_DOCUMENTS = {
    ".pdf": {
        "content_types": {"application/pdf"},
        "label": "PDF",
    },
    ".jpg": {
        "content_types": {"image/jpeg"},
        "image_formats": {"JPEG"},
        "label": "JPG",
    },
    ".jpeg": {
        "content_types": {"image/jpeg"},
        "image_formats": {"JPEG"},
        "label": "JPEG",
    },
    ".png": {
        "content_types": {"image/png"},
        "image_formats": {"PNG"},
        "label": "PNG",
    },
    ".webp": {
        "content_types": {"image/webp"},
        "image_formats": {"WEBP"},
        "label": "WebP",
    },
}


def _validate_uploaded_filename(uploaded_file) -> None:
    raw_name = str(getattr(uploaded_file, "name", "") or "")
    if "/" in raw_name or "\\" in raw_name:
        raise ValidationError(_("Имя файла не должно содержать пути или вложенные каталоги."))

    normalized_name = Path(raw_name).name

    if not normalized_name:
        raise ValidationError(_("У файла должно быть имя."))

    if raw_name != normalized_name:
        raise ValidationError(_("Имя файла не должно содержать пути или вложенные каталоги."))

    max_length = int(getattr(settings, "MAX_UPLOAD_FILENAME_LENGTH", 180))
    if len(normalized_name) > max_length:
        raise ValidationError(
            _("Имя файла слишком длинное. Максимум: %(length)s символов.") % {"length": max_length}
        )

    if any(ord(char) < 32 for char in normalized_name):
        raise ValidationError(_("Имя файла содержит недопустимые управляющие символы."))


def _get_pdf_reader():
    for module_name in ("pypdf", "PyPDF2"):
        try:
            module = import_module(module_name)
            return getattr(module, "PdfReader", None)
        except ImportError:
            continue
    return None


def _reset_position(uploaded_file, position: int) -> None:
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(position)


def _validate_pdf_file(uploaded_file) -> None:
    start_position = uploaded_file.tell()
    try:
        uploaded_file.seek(0)
        payload = uploaded_file.read()
        if not payload.startswith(b"%PDF-"):
            raise ValidationError(_("Загрузите корректный PDF-файл."))
        if b"%%EOF" not in payload:
            raise ValidationError(_("PDF-файл повреждён или не читается."))
        if b"/Encrypt" in payload:
            raise ValidationError(_("PDF-файлы, защищённые паролем, не поддерживаются."))

        pdf_reader = _get_pdf_reader()
        if pdf_reader is None:
            return

        uploaded_file.seek(0)
        reader = pdf_reader(uploaded_file)
        if getattr(reader, "is_encrypted", False):
            raise ValidationError(_("PDF-файлы, защищённые паролем, не поддерживаются."))
        if not reader.pages:
            raise ValidationError(_("PDF-файл повреждён или пуст."))
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError(_("PDF-файл повреждён или не читается.")) from exc
    finally:
        _reset_position(uploaded_file, start_position)


def _validate_image_file(uploaded_file, *, allowed_formats: set[str], label: str) -> None:
    start_position = uploaded_file.tell()
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:  # pragma: no cover - dependency is installed in app/runtime
        raise ValidationError(_("Проверка изображений сейчас недоступна.")) from exc

    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as image:
            image_format = (image.format or "").upper()
            width, height = image.size
            max_pixels = int(getattr(settings, "MAX_IMAGE_PIXELS", 25_000_000))
            if width * height > max_pixels:
                raise ValidationError(
                    _("Разрешение изображения слишком большое. Максимум: %(pixels)s пикселей.")
                    % {"pixels": max_pixels}
                )
            image.verify()
        if image_format not in allowed_formats:
            raise ValidationError(_("Загрузите корректный файл %(label)s.") % {"label": label})
    except ValidationError:
        raise
    except UnidentifiedImageError as exc:
        raise ValidationError(_("Загрузите корректное изображение %(label)s.") % {"label": label}) from exc
    except Exception as exc:
        raise ValidationError(_("Файл изображения повреждён или не читается.")) from exc
    finally:
        _reset_position(uploaded_file, start_position)


def validate_uploaded_document(uploaded_file):
    if uploaded_file is None:
        raise ValidationError(_("Выберите файл для загрузки."))

    _validate_uploaded_filename(uploaded_file)

    max_size = int(getattr(settings, "MAX_UPLOAD_SIZE_MB", 20)) * 1024 * 1024
    if getattr(uploaded_file, "size", 0) > max_size:
        raise ValidationError(
            _("Файл слишком большой. Максимальный размер: %(size)s МБ.")
            % {"size": getattr(settings, "MAX_UPLOAD_SIZE_MB", 20)}
        )

    extension = Path(getattr(uploaded_file, "name", "")).suffix.lower()
    config = ALLOWED_DOCUMENTS.get(extension)
    if config is None:
        raise ValidationError(_("Разрешены только PDF, JPG, JPEG, PNG и WebP файлы."))

    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    if content_type and content_type not in config["content_types"]:
        raise ValidationError(_("Недопустимый MIME-тип файла: %(type)s.") % {"type": content_type})

    if extension == ".pdf":
        _validate_pdf_file(uploaded_file)
    else:
        _validate_image_file(
            uploaded_file,
            allowed_formats=set(config.get("image_formats", set())),
            label=str(config["label"]),
        )

    return uploaded_file
