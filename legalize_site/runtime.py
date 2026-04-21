from __future__ import annotations

import importlib.util
import shutil
from typing import Any

from django.conf import settings


def collect_runtime_dependency_statuses() -> list[dict[str, Any]]:
    """Return runtime dependency availability for diagnostics and system checks."""

    statuses: list[dict[str, Any]] = []

    package_checks = [
        {
            "key": "pdf2image",
            "label": "pdf2image",
            "kind": "python",
            "required_for": "OCR on PDF scans",
            "hint": "Install the `pdf2image` package from requirements.txt.",
        },
        {
            "key": "pytesseract",
            "label": "pytesseract",
            "kind": "python",
            "required_for": "OCR text extraction",
            "hint": "Install the `pytesseract` package from requirements.txt.",
        },
    ]

    binary_checks = [
        {
            "key": "tesseract",
            "label": "tesseract",
            "kind": "binary",
            "required_for": "OCR text extraction",
            "hint": "Install the Tesseract binary and make it available in PATH.",
        },
        {
            "key": "pdftoppm",
            "label": "pdftoppm",
            "kind": "binary",
            "required_for": "OCR on PDF scans",
            "hint": "Install Poppler utilities so `pdftoppm` is available in PATH.",
        },
        {
            "key": "pg_dump",
            "label": "pg_dump",
            "kind": "binary",
            "required_for": "database backups",
            "hint": "Install PostgreSQL client tools so `pg_dump` is available in PATH.",
        },
    ]

    if getattr(settings, "ENABLE_TRANSLATION_TOOLING", False):
        binary_checks.append(
            {
                "key": "msgfmt",
                "label": "msgfmt",
                "kind": "binary",
                "required_for": "gettext compilation",
                "hint": "Install gettext tools so `compilemessages` can use `msgfmt`.",
            }
        )

    for check in package_checks:
        available = importlib.util.find_spec(check["key"]) is not None
        statuses.append(
            {
                **check,
                "available": available,
                "status": "ok" if available else "missing",
                "css": "success" if available else "warning",
            }
        )

    for check in binary_checks:
        available = shutil.which(check["key"]) is not None
        statuses.append(
            {
                **check,
                "available": available,
                "status": "ok" if available else "missing",
                "css": "success" if available else "warning",
            }
        )

    return statuses


def runtime_dependency_summary() -> dict[str, Any]:
    statuses = collect_runtime_dependency_statuses()
    missing = [item for item in statuses if not item["available"]]
    return {
        "status": "degraded" if missing else "ok",
        "total": len(statuses),
        "missing_count": len(missing),
        "missing_keys": [item["key"] for item in missing],
        "dependencies": statuses,
    }
