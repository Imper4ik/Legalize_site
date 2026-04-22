from __future__ import annotations

from pathlib import Path

from django.http import FileResponse, Http404

from clients.services.responses import apply_no_store


def build_protected_file_response(file_field, *, filename: str | None = None, as_attachment: bool = True):
    if not file_field:
        raise Http404("File not found")
    try:
        file_handle = file_field.open("rb")
    except FileNotFoundError as exc:
        raise Http404("File not found") from exc

    resolved_name = filename or Path(file_field.name).name
    response = FileResponse(file_handle, as_attachment=as_attachment, filename=resolved_name)
    return apply_no_store(response)
