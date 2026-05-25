from __future__ import annotations

import logging
import os
import re
import tempfile
from typing import Any

from django.db import IntegrityError
from django.utils.translation import gettext as _

from clients.constants import COMPANY_DOCUMENT_TYPES, DocumentType
from clients.models import Document, DocumentProcessingJob

logger = logging.getLogger(__name__)

_ALLOWED_STANDARD_INSURANCE_PREFIXES = ("0110", "0411", "0412", "0444")


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


def _patch_process_zus_doc_job_internal() -> None:
    from clients.services import document_workflow as workflow

    def _process_zus_doc_job_internal(
        job: DocumentProcessingJob,
        source_file_name: str,
        document_file: Any,
    ) -> Any:
        from clients.services.zus_parser import parse_zus_doc
        try:
            with document_file.open("rb") as src:
                ext = os.path.splitext(document_file.name or "")[1]
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                    for chunk in src.chunks():
                        tmp.write(chunk)
                    tmp_path = tmp.name
            try:
                parsed = parse_zus_doc(tmp_path)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
        except Exception as exc:
            logger.warning(
                "Automatic ZUS document parsing failed for queued job %s: error_type=%s",
                job.id,
                type(exc).__name__,
            )
            return workflow._finalize_failed_ocr_job(
                job_id=job.id,
                source_file_name=source_file_name,
                error_message=str(_("Automatic ZUS document parsing failed.")),
            )

        if parsed.error == "no_text":
            return workflow._finalize_failed_ocr_job(
                job_id=job.id,
                source_file_name=source_file_name,
                error_message=str(_("Could not extract any text from the ZUS document.")),
            )

        document = job.document
        client = document.client
        warnings: list[str] = []
        infos: list[str] = []

        # 1. Verify name.
        name_matched = workflow._check_client_name_in_document(client, parsed.detected_names, parsed.text)
        if not name_matched:
            warnings.append(str(_("Client name not matched in the ZUS document.")))

        # 2. Verify / auto-fill ZUS RCA reporting month.
        is_registration_form = False
        form_type = getattr(parsed, "zus_form_type", None)
        if form_type in ("ZUA", "ZCNA"):
            is_registration_form = True
        elif parsed.text:
            normalized_text = parsed.text.upper()
            if "ZUS ZUA" in normalized_text or "ZUS ZCNA" in normalized_text:
                is_registration_form = True

        if is_registration_form:
            detected_month = None
            saved_month = None
            display_month = None
            month_mismatch = False
            if document.zus_period_month is not None:
                document.zus_period_month = None
                document.save(update_fields=["zus_period_month"])
        else:
            detected_month = getattr(parsed, "period_month", None)
            month_warnings, month_infos, month_mismatch, final_month = _build_zus_month_status(
                document,
                detected_month,
            )
            warnings.extend(month_warnings)
            infos.extend(month_infos)
            saved_month, assignment_message = _safe_assign_zus_month(document, final_month)
            if assignment_message:
                if saved_month == final_month:
                    infos.append(assignment_message)
                else:
                    warnings.append(assignment_message)

            display_month = saved_month or final_month or _normalize_month(document.zus_period_month)

        # 3. Verify employer NIP.
        contract_nip = None
        company_docs = Document.objects.filter(
            client=client,
            document_type__in=list(COMPANY_DOCUMENT_TYPES),
            ocr_status__in=["success", "completed"],
        )
        for doc in company_docs:
            if doc.parsed_data and isinstance(doc.parsed_data, dict):
                nip_val = doc.parsed_data.get("nip")
                if nip_val:
                    contract_nip = re.sub(r"[^\d]", "", str(nip_val))
                    break

        if parsed.employer_nip:
            zus_nip_clean = re.sub(r"[^\d]", "", parsed.employer_nip)
            if contract_nip:
                if zus_nip_clean != contract_nip:
                    warnings.append(
                        str(_("ZUS employer NIP (%(zus_nip)s) does not match contract NIP (%(contract_nip)s).") % {
                            "zus_nip": parsed.employer_nip,
                            "contract_nip": contract_nip,
                        })
                    )
            else:
                from clients.services.company_parser import validate_nip

                if not validate_nip(zus_nip_clean):
                    warnings.append(str(_("Extracted employer NIP %(nip)s is invalid.") % {"nip": parsed.employer_nip}))
        else:
            warnings.append(str(_("Could not extract employer NIP from the ZUS document.")))

        # 4. Check insurance code. 0444 is a real code in this workflow, so do not warn.
        if parsed.insurance_code:
            if not parsed.insurance_code.startswith(_ALLOWED_STANDARD_INSURANCE_PREFIXES):
                warnings.append(
                    str(_("Insurance code '%(code)s' indicates non-standard employment type (expected Umowa o pracę/zlecenie).") % {
                        "code": parsed.insurance_code,
                    })
                )
            else:
                infos.append(
                    str(_("Insurance code %(code)s accepted.") % {"code": parsed.insurance_code})
                )
        else:
            warnings.append(str(_("Could not extract insurance code (e.g. 011000) from ZUS.")))

        parsed_payload = {
            "employer_nip": parsed.employer_nip,
            "insurance_code": parsed.insurance_code,
            "detected_names": parsed.detected_names,
            "ocr_month": detected_month.isoformat() if detected_month else None,
            "ocr_month_display": _format_month(detected_month) if detected_month else "",
            "manual_month": saved_month.isoformat() if saved_month else None,
            "manual_month_display": _format_month(saved_month) if saved_month else "",
            "detected_month": display_month.isoformat() if display_month else None,
            "detected_month_display": _format_month(display_month) if display_month else "",
            "month_mismatch": month_mismatch,
            "warnings": warnings,
            "infos": infos,
            "has_name_mismatch": not name_matched,
        }

        return workflow._finalize_successful_ocr_job(
            job_id=job.id,
            source_file_name=source_file_name,
            parsed_payload=parsed_payload,
            warnings=warnings,
            doc_type_display=str(_("ZUS Document")),
        )

    workflow._process_zus_doc_job_internal = _process_zus_doc_job_internal


def apply_zus_workflow_patch() -> None:
    """Install runtime fixes for ZUS OCR month handling.

    Kept as a small patch module so the existing workflow implementation can stay
    compatible with older migrations while ZUS RCA logic gains month detection and
    correct handling of real 0444 insurance codes.
    """
    _patch_process_zus_doc_job_internal()
