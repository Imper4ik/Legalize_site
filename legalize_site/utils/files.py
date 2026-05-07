from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, TYPE_CHECKING

from django.http import FileResponse, Http404, HttpResponse

from clients.services.responses import apply_no_store

if TYPE_CHECKING:
    from django.http.response import HttpResponseBase


mimetypes.add_type("image/webp", ".webp", True)
mimetypes.add_type("image/webp", ".webp", False)


def _guess_content_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()

    explicit_types = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }

    if suffix in explicit_types:
        return explicit_types[suffix]

    guessed_type, _encoding = mimetypes.guess_type(filename)
    return guessed_type or "application/octet-stream"


def build_protected_file_response(
    file_field: Any,
    *,
    filename: str | None = None,
    as_attachment: bool = True,
    content_type: str | None = None,
) -> HttpResponseBase:
    if not file_field:
        raise Http404("File not found")

    try:
        file_handle = file_field.open("rb")
    except FileNotFoundError as exc:
        raise Http404("File not found") from exc

    resolved_name = filename or Path(str(file_field.name)).name
    resolved_content_type = content_type or _guess_content_type(resolved_name or str(file_field.name))

    response = FileResponse(
        file_handle,
        as_attachment=as_attachment,
        filename=resolved_name,
        content_type=resolved_content_type,
    )

    response["X-Content-Type-Options"] = "nosniff"
    return apply_no_store(response)
