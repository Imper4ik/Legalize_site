"""ZUS month resolution helpers, extracted from ``document_workflow``.

Self-contained utilities for reconciling the manually selected ZUS period
month with the month detected by OCR, and safely assigning it without
violating the active-document uniqueness constraint. Imported back into
``document_workflow`` so callers and mock targets are unaffected.
"""
from __future__ import annotations

import logging
from typing import Any

from django.db import IntegrityError
from django.utils.translation import gettext as _

from clients.models import Document

logger = logging.getLogger(__name__)


def _format_month(value: Any) -> str:
    if not value:
        return "-"
    return value.strftime("%m.%Y") if hasattr(value, "strftime") else str(value)


def _normalize_month(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "replace"):
        return value.replace(day=1)
    return value


def _build_zus_month_status(document: Document, ocr_month: Any) -> tuple[list[str], list[str], bool, Any]:
    warnings: list[str] = []
    infos: list[str] = []
    month_mismatch = False
    final_month = _normalize_month(document.zus_period_month)
    ocr_month = _normalize_month(ocr_month)

    if ocr_month and not final_month:
        final_month = ocr_month
        infos.append(
            str(_("ZUS month was detected by OCR: %(month)s") % {
                "month": _format_month(ocr_month),
            })
        )
    elif ocr_month and final_month and final_month != ocr_month:
        month_mismatch = True
        warnings.append(
            str(_("ZUS month mismatch: selected %(manual)s, OCR found %(ocr)s.") % {
                "manual": _format_month(final_month),
                "ocr": _format_month(ocr_month),
            })
        )
    elif not ocr_month and not final_month:
        warnings.append(str(_("ZUS month is not set and OCR could not detect it.")))
    elif not ocr_month and final_month:
        infos.append(
            str(_("OCR could not detect the ZUS month; using the manually selected month %(month)s.") % {
                "month": _format_month(final_month),
            })
        )
    elif ocr_month and final_month == ocr_month:
        infos.append(
            str(_("ZUS month confirmed by OCR: %(month)s") % {
                "month": _format_month(ocr_month),
            })
        )

    return warnings, infos, month_mismatch, final_month


def _safe_assign_zus_month(document: Document, final_month: Any) -> tuple[Any, str | None]:
    """Assign OCR-detected ZUS month without violating active-document uniqueness."""
    if not final_month or document.zus_period_month == final_month:
        return document.zus_period_month, None

    duplicate_exists = Document.objects.filter(
        client_id=document.client_id,
        document_type=document.document_type,
        zus_period_month=final_month,
    ).exclude(pk=document.pk).exists()

    if duplicate_exists:
        return None, str(
            _("ZUS RCA for %(month)s already exists. OCR month is shown below but was not saved to avoid an active duplicate.")
            % {"month": _format_month(final_month)}
        )

    try:
        document.zus_period_month = final_month
        document.save(update_fields=["zus_period_month"])
        return document.zus_period_month, str(
            _("ZUS month was saved automatically: %(month)s") % {"month": _format_month(final_month)}
        )
    except IntegrityError:
        logger.info(
            "Skipped duplicate OCR ZUS month assignment: document_id=%s client_id=%s month=%s",
            document.pk,
            document.client_id,
            final_month,
        )
        document.zus_period_month = None
        return None, str(
            _("ZUS RCA for %(month)s already exists. OCR month is shown below but was not saved to avoid an active duplicate.")
            % {"month": _format_month(final_month)}
        )
