"""Per-type OCR job processors and finalizers.

Each ``_process_*_doc_job_internal`` consumes a claimed DocumentProcessingJob,
runs the matching parser over a temp copy of the file and persists the outcome
via the ``_finalize_*`` helpers. Extracted from ``document_workflow``; the
dispatcher lives in ``document_jobs``.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, cast

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from clients.constants import DocumentType
from clients.models import Case, Client, Document, DocumentProcessingJob
from clients.services.activity import log_client_activity
from clients.services.company_parser import parse_company_doc
from clients.services.document_processing_common import (
    MANUAL_WEZWANIE_REVIEW_MESSAGE,
    DocumentProcessingRunResult,
    NotificationSender,
    _job_matches_processing_state,
)
from clients.services.document_workflow_wezwanie import (
    _append_required_documents_update,
    _apply_parsed_client_updates,
    _build_wezwanie_payload,
    _has_name_mismatch,
)
from clients.services.document_workflow_zus import (
    _build_zus_month_status,
    _format_month,
    _normalize_month,
    _safe_assign_zus_month,
)
from clients.services.registry_api import match_names, normalize_string, verify_employer
from clients.services.wezwanie_parser import WezwanieData

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _check_client_name_in_document(client: Client, detected_names: list[str], text: str) -> bool:
    """
    Checks if client's name matches one of the detected names,
    or if both first name and last name are found in the text.
    """
    client_full_name = client.get_full_name()
    if detected_names:
        matched = match_names(detected_names, [client_full_name])
        if matched:
            return True

    # Fallback check on raw text
    norm_text = normalize_string(text)
    norm_first = normalize_string(client.first_name)
    norm_last = normalize_string(client.last_name)
    if norm_first and norm_last:
        if norm_first in norm_text and norm_last in norm_text:
            return True
    return False


def _process_company_doc_job_internal(
    job: DocumentProcessingJob,
    source_file_name: str,
    document_file: Any,
) -> DocumentProcessingRunResult:
    try:
        with document_file.open("rb") as src:
            ext = os.path.splitext(document_file.name or "")[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                for chunk in src.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
        try:
            parsed = parse_company_doc(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as exc:
        logger.warning(
            "Automatic company doc parsing failed for queued job %s: error_type=%s",
            job.id,
            type(exc).__name__,
        )
        return _finalize_failed_company_job(
            job_id=job.id,
            source_file_name=source_file_name,
            error_message=str(_("Automatic company doc parsing failed.")),
        )

    # Call registry verification
    try:
        report = verify_employer(
            nip=parsed.nip,
            krs=parsed.krs,
            detected_names=parsed.detected_names,
        )
    except Exception as exc:
        logger.warning(
            "Registry verification failed for job %s: error_type=%s",
            job.id,
            type(exc).__name__,
        )
        report = {
            "registry_source": None,
            "company_name": None,
            "is_employer_active": False,
            "nip": parsed.nip,
            "krs": parsed.krs,
            "representatives": [],
            "signer_authorized": False,
            "matched_signer": None,
            "warnings": [f"Registry query failed with error: {str(exc)}"]
        }

    # Minimum salary check (4300 PLN as of 2026)
    MIN_SALARY = 4300.0
    if parsed.salary is not None:
        if parsed.salary < MIN_SALARY:
            report["warnings"].append(
                str(_("Salary %(salary)s PLN is below the statutory minimum of %(min)s PLN.") % {
                    "salary": parsed.salary,
                    "min": MIN_SALARY
                })
            )
    else:
        report["warnings"].append(str(_("Could not extract salary from the document.")))

    parsed_payload = {
        "nip": parsed.nip,
        "krs": parsed.krs,
        "salary": parsed.salary,
        "valid_until": parsed.valid_until.isoformat() if parsed.valid_until else None,
        "detected_names": parsed.detected_names,
        "registry_verification": report,
        "has_name_mismatch": not report.get("signer_authorized", True),
    }


    return _finalize_successful_company_job(
        job_id=job.id,
        source_file_name=source_file_name,
        parsed_payload=parsed_payload,
        warnings=report["warnings"],
    )


def _process_passport_doc_job_internal(
    job: DocumentProcessingJob,
    source_file_name: str,
    document_file: Any,
) -> DocumentProcessingRunResult:
    from clients.services.passport_parser import parse_passport_doc

    try:
        with document_file.open("rb") as src:
            ext = os.path.splitext(document_file.name or "")[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                for chunk in src.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
        try:
            parsed = parse_passport_doc(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as exc:
        logger.warning(
            "Automatic passport parsing failed for queued job %s: error_type=%s",
            job.id,
            type(exc).__name__,
        )
        return _finalize_failed_ocr_job(
            job_id=job.id,
            source_file_name=source_file_name,
            error_message=str(_("Automatic passport parsing failed.")),
        )

    if parsed.error == "no_text":
        return _finalize_failed_ocr_job(
            job_id=job.id,
            source_file_name=source_file_name,
            error_message=str(_("Could not extract any text from the passport.")),
        )

    client = job.document.client
    warnings = []
    auto_updates = []

    # 1. Verify Name
    passport_names = []
    if parsed.first_name and parsed.last_name:
        passport_names.append(f"{parsed.first_name} {parsed.last_name}")

    name_matched = _check_client_name_in_document(client, passport_names, parsed.text)
    if not name_matched:
        warnings.append(str(_("Client name not matched in the passport.")))

    # 2. Verify DOB
    if parsed.date_of_birth and client.birth_date:
        if parsed.date_of_birth != client.birth_date:
            warnings.append(
                str(_("Passport Date of Birth (%(passport_dob)s) does not match Client DOB (%(client_dob)s).") % {
                    "passport_dob": parsed.date_of_birth.isoformat(),
                    "client_dob": client.birth_date.isoformat(),
                })
            )
    elif not parsed.date_of_birth:
        warnings.append(str(_("Could not extract Date of Birth from the passport.")))

    # 3. Verify validity/expiry
    if parsed.valid_until:
        if parsed.valid_until < date.today():
            warnings.append(
                str(_("Passport has expired on %(expiry)s.") % {"expiry": parsed.valid_until.isoformat()})
            )
        elif parsed.valid_until <= date.today() + timedelta(days=90):
            warnings.append(
                str(_("Passport expires soon (%(expiry)s), in less than 3 months.") % {"expiry": parsed.valid_until.isoformat()})
            )
    else:
        warnings.append(str(_("Could not extract Passport expiration date.")))

    # 4. Auto-update passport number if missing in DB
    if parsed.passport_number:
        passport_num_clean = re.sub(r"\s+", "", parsed.passport_number).upper()
        if not client.passport_num:
            client.passport_num = passport_num_clean
            client.save(update_fields=["passport_num"])
            auto_updates.append(f"Updated missing client passport number to: {passport_num_clean}")
        elif client.passport_num.replace(" ", "").upper() != passport_num_clean:
            warnings.append(
                str(_("Passport number in document (%(doc_num)s) does not match profile (%(profile_num)s).") % {
                    "doc_num": passport_num_clean,
                    "profile_num": client.passport_num,
                })
            )

    parsed_payload = {
        "passport_number": parsed.passport_number,
        "first_name": parsed.first_name,
        "last_name": parsed.last_name,
        "date_of_birth": parsed.date_of_birth.isoformat() if parsed.date_of_birth else None,
        "valid_until": parsed.valid_until.isoformat() if parsed.valid_until else None,
        "country": parsed.country,
        "warnings": warnings,
        "auto_updates": auto_updates,
        "has_name_mismatch": not name_matched,
    }

    return _finalize_successful_ocr_job(
        job_id=job.id,
        source_file_name=source_file_name,
        parsed_payload=parsed_payload,
        warnings=warnings,
        doc_type_display=str(_("Passport")),
    )


def _process_rental_doc_job_internal(
    job: DocumentProcessingJob,
    source_file_name: str,
    document_file: Any,
) -> DocumentProcessingRunResult:
    from clients.services.rental_parser import parse_rental_doc

    try:
        with document_file.open("rb") as src:
            ext = os.path.splitext(document_file.name or "")[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                for chunk in src.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
        try:
            parsed = parse_rental_doc(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as exc:
        logger.warning(
            "Automatic rental agreement parsing failed for queued job %s: error_type=%s",
            job.id,
            type(exc).__name__,
        )
        return _finalize_failed_ocr_job(
            job_id=job.id,
            source_file_name=source_file_name,
            error_message=str(_("Automatic rental agreement parsing failed.")),
        )

    if parsed.error == "no_text":
        return _finalize_failed_ocr_job(
            job_id=job.id,
            source_file_name=source_file_name,
            error_message=str(_("Could not extract any text from the rental agreement.")),
        )

    client = job.document.client
    warnings = []

    # 1. Verify Name
    name_matched = _check_client_name_in_document(client, parsed.detected_names, parsed.text)
    if not name_matched:
        warnings.append(str(_("Client name not matched in the rental agreement.")))

    # 2. Verify Address (case-scoped: only this document's case MOS data)
    from clients.models import MOSApplicationData
    mos_data = (
        MOSApplicationData.objects.filter(case=job.document.case).first()
        if job.document.case_id
        else None
    )
    if mos_data and mos_data.address_data:
        address_data = cast("dict[str, Any]", mos_data.address_data)
        street = address_data.get("street", "").strip()
        city = address_data.get("city", "").strip()
        postal_code = address_data.get("postal_code", "").strip()

        if street or city or postal_code:
            norm_parsed_addr = normalize_string(parsed.address or "")
            norm_street = normalize_string(street)
            norm_city = normalize_string(city)
            norm_postcode = re.sub(r"\D", "", postal_code)
            norm_parsed_postcode = re.sub(r"\D", "", parsed.address or "")

            has_street = norm_street in norm_parsed_addr if norm_street else True
            has_city = norm_city in norm_parsed_addr if norm_city else True
            has_postcode = norm_postcode in norm_parsed_postcode if norm_postcode else True

            if not (has_street and has_city and has_postcode):
                warnings.append(
                    str(_("Agreement address does not match onboarding address: %(onboarding_addr)s.") % {
                        "onboarding_addr": f"{street}, {postal_code} {city}".strip(", "),
                    })
                )
        else:
            warnings.append(str(_("Address details are not filled in onboarding profile.")))
    else:
        warnings.append(str(_("Onboarding address data not found.")))

    # 3. Verify validity/expiry
    if parsed.valid_until:
        if parsed.valid_until < date.today():
            warnings.append(
                str(_("Rental agreement has expired on %(expiry)s.") % {"expiry": parsed.valid_until.isoformat()})
            )

    parsed_payload = {
        "address": parsed.address,
        "valid_until": parsed.valid_until.isoformat() if parsed.valid_until else None,
        "monthly_cost": parsed.monthly_cost,
        "detected_names": parsed.detected_names,
        "warnings": warnings,
        "has_name_mismatch": not name_matched,
    }

    return _finalize_successful_ocr_job(
        job_id=job.id,
        source_file_name=source_file_name,
        parsed_payload=parsed_payload,
        warnings=warnings,
        doc_type_display=str(_("Rental Agreement")),
    )


_ALLOWED_STANDARD_INSURANCE_PREFIXES = ("0110", "0411", "0412", "0444")


def _process_zus_doc_job_internal(
    job: DocumentProcessingJob,
    source_file_name: str,
    document_file: Any,
) -> DocumentProcessingRunResult:
    from clients.services.zus_parser import parse_zus_doc

    try:
        with document_file.open("rb") as src:
            ext = os.path.splitext(document_file.name or "")[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                for chunk in src.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
        try:
            # The checklist slot is trusted context: a document in the RCA slot
            # gets the month fallback even when photo OCR mangles "RCA" itself.
            parsed = parse_zus_doc(
                tmp_path,
                assume_rca=(
                    job.document.document_type == DocumentType.ZUS_RCA_OR_INSURANCE.value
                ),
            )
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as exc:
        logger.warning(
            "Automatic ZUS document parsing failed for queued job %s: error_type=%s",
            job.id,
            type(exc).__name__,
        )
        return _finalize_failed_ocr_job(
            job_id=job.id,
            source_file_name=source_file_name,
            error_message=str(_("Automatic ZUS document parsing failed.")),
        )

    if parsed.error == "no_text":
        return _finalize_failed_ocr_job(
            job_id=job.id,
            source_file_name=source_file_name,
            error_message=str(_("Could not extract any text from the ZUS document.")),
        )

    document = job.document
    client = document.client
    warnings: list[str] = []
    infos: list[str] = []

    # 1. Verify name.
    name_matched = _check_client_name_in_document(client, parsed.detected_names, parsed.text)
    if not name_matched:
        warnings.append(str(_("Client name not matched in the ZUS document.")))

    # 2. Verify / auto-fill ZUS RCA reporting month.
    is_registration_form = False
    form_type = getattr(parsed, "zus_form_type", None)
    if form_type in ("ZUA", "ZCNA", "ZZA", "ZWUA"):
        is_registration_form = True
    elif parsed.text:
        normalized_text = parsed.text.upper()
        if any(t in normalized_text for t in ("ZUS ZUA", "ZUS ZCNA", "ZUS ZZA", "ZUS ZWUA")):
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
    from clients.constants import COMPANY_DOCUMENT_TYPES
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
        # ZCNA may not always contain employer NIP in a standard location
        if form_type != "ZCNA":
            warnings.append(str(_("Could not extract employer NIP from the ZUS document.")))

    # 4. Check insurance code. 0444 is a real code in this workflow, so do not warn.
    if form_type != "ZCNA":
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

    # Build form-specific display name
    if form_type:
        doc_type_label = str(_("ZUS %(form_type)s")) % {"form_type": form_type}
    else:
        doc_type_label = str(_("ZUS Document"))

    parsed_payload = {
        "employer_nip": parsed.employer_nip,
        "insurance_code": parsed.insurance_code,
        "detected_names": parsed.detected_names,
        "zus_form_type": form_type,
        "period_month": detected_month.isoformat() if detected_month else None,
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

    result = _finalize_successful_ocr_job(
        job_id=job.id,
        source_file_name=source_file_name,
        parsed_payload=parsed_payload,
        warnings=warnings,
        doc_type_display=doc_type_label,
    )
    if parsed.employer_nip:
        from clients.services.employers import propose_employer
        propose_employer(
            case=document.case,
            nip=parsed.employer_nip,
            document=document,
            source="zus_ocr",
            confidence="ocr",
        )
    return result


def _process_insurance_doc_job_internal(
    job: DocumentProcessingJob,
    source_file_name: str,
    document_file: Any,
) -> DocumentProcessingRunResult:
    from clients.services.insurance_parser import parse_insurance_doc

    try:
        with document_file.open("rb") as src:
            ext = os.path.splitext(document_file.name or "")[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                for chunk in src.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
        try:
            parsed = parse_insurance_doc(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as exc:
        logger.warning(
            "Automatic insurance parsing failed for queued job %s: error_type=%s",
            job.id,
            type(exc).__name__,
        )
        return _finalize_failed_ocr_job(
            job_id=job.id,
            source_file_name=source_file_name,
            error_message=str(_("Automatic insurance parsing failed.")),
        )

    if parsed.error == "no_text":
        return _finalize_failed_ocr_job(
            job_id=job.id,
            source_file_name=source_file_name,
            error_message=str(_("Could not extract any text from the insurance document.")),
        )

    # The "ZUS RCA or insurance" slot routes to the insurance parser whenever the
    # ZUS reporting month has not been selected manually. A ZUS RCA (or any other
    # ZUS form) uploaded without a month would otherwise be verified as a private
    # insurance policy and produce misleading "missing coverage/expiry" warnings.
    # Re-route to the ZUS parser when the OCR text clearly identifies a ZUS form.
    if job.document.document_type == DocumentType.ZUS_RCA_OR_INSURANCE.value:
        from clients.services.zus_parser import _detect_zus_form_type

        if _detect_zus_form_type(parsed.text):
            logger.info(
                "Re-routing ZUS_RCA_OR_INSURANCE job %s from insurance to ZUS parsing "
                "(detected ZUS form in OCR text).",
                job.id,
            )
            return _process_zus_doc_job_internal(job, source_file_name, document_file)

    client = job.document.client
    warnings = []

    # 1. Verify Name
    name_matched = _check_client_name_in_document(client, parsed.detected_names, parsed.text)
    if not name_matched:
        warnings.append(str(_("Client name not matched in the insurance policy.")))

    # 2. Verify validity/expiry
    if parsed.valid_until:
        if parsed.valid_until < date.today():
            warnings.append(
                str(_("Insurance policy has expired on %(expiry)s.") % {"expiry": parsed.valid_until.isoformat()})
            )
    else:
        warnings.append(str(_("Could not extract insurance expiration date.")))

    # 3. Verify Coverage Limit (>= 30,000 EUR or >= 120,000 PLN)
    if parsed.coverage_amount and parsed.currency:
        if parsed.currency == "EUR" and parsed.coverage_amount < 30000.0:
            warnings.append(
                str(_("Insurance coverage limit (%(amount)s EUR) is below the statutory minimum of 30,000 EUR.") % {
                    "amount": parsed.coverage_amount
                })
            )
        elif parsed.currency == "PLN" and parsed.coverage_amount < 120000.0:
            warnings.append(
                str(_("Insurance coverage limit (%(amount)s PLN) is below the statutory minimum of 120,000 PLN.") % {
                    "amount": parsed.coverage_amount
                })
            )
        elif parsed.currency not in ("EUR", "PLN"):
            warnings.append(
                str(_("Insurance coverage currency is '%(curr)s' (expected EUR or PLN). Cannot verify coverage limit.") % {
                    "curr": parsed.currency
                })
            )
    else:
        warnings.append(str(_("Could not extract insurance coverage amount or currency (min 30,000 EUR / 120,000 PLN).")))

    parsed_payload = {
        "valid_until": parsed.valid_until.isoformat() if parsed.valid_until else None,
        "coverage_amount": parsed.coverage_amount,
        "currency": parsed.currency,
        "detected_names": parsed.detected_names,
        "warnings": warnings,
        "has_name_mismatch": not name_matched,
    }

    return _finalize_successful_ocr_job(
        job_id=job.id,
        source_file_name=source_file_name,
        parsed_payload=parsed_payload,
        warnings=warnings,
        doc_type_display=str(_("Health Insurance")),
    )


def _finalize_failed_company_job(
    *,
    job_id: int,
    source_file_name: str,
    error_message: str,
) -> DocumentProcessingRunResult:
    with transaction.atomic():
        job = DocumentProcessingJob.objects.select_for_update().get(pk=job_id)
        job.status = DocumentProcessingJob.STATUS_FAILED
        job.error_message = error_message
        job.completed_at = timezone.now()
        job.source_file_name = source_file_name
        job.save(update_fields=["status", "error_message", "completed_at", "source_file_name"])

        document = job.document
        document.ocr_status = "failed"
        document.save(update_fields=["ocr_status"])

    return DocumentProcessingRunResult(
        job=job,
        status=DocumentProcessingJob.STATUS_FAILED,
        processed=False,
        message=error_message,
        manual_review_required=True,
    )


def _finalize_successful_company_job(
    *,
    job_id: int,
    source_file_name: str,
    parsed_payload: dict[str, Any],
    warnings: list[str],
) -> DocumentProcessingRunResult:
    with transaction.atomic():
        job = DocumentProcessingJob.objects.select_for_update().get(pk=job_id)
        job.status = DocumentProcessingJob.STATUS_COMPLETED
        job.completed_at = timezone.now()
        job.error_message = ""
        job.source_file_name = source_file_name
        job.save(update_fields=["status", "completed_at", "error_message", "source_file_name"])

        document = job.document
        document.parsed_data = parsed_payload
        document.ocr_status = "success"
        document.ocr_name_mismatch = bool(warnings)
        document.save(update_fields=["parsed_data", "ocr_status", "ocr_name_mismatch"])

    from clients.services.employers import propose_employer
    registry = parsed_payload.get("registry_verification") or {}
    propose_employer(
        case=document.case,
        name=str(registry.get("company_name") or ""),
        nip=str(parsed_payload.get("nip") or ""),
        krs=str(parsed_payload.get("krs") or ""),
        document=document,
        source="company_document_ocr",
        confidence="registry" if registry.get("company_name") else "ocr",
    )

    msg = (
        _("Company document verified successfully with %(warning_count)s warnings.") % {
            "warning_count": len(warnings)
        }
        if warnings else
        _("Company document verified successfully.")
    )
    return DocumentProcessingRunResult(
        job=job,
        status=DocumentProcessingJob.STATUS_COMPLETED,
        processed=True,
        message=msg,
        manual_review_required=bool(warnings),
    )


def _finalize_failed_ocr_job(
    *,
    job_id: int,
    source_file_name: str,
    error_message: str,
) -> DocumentProcessingRunResult:
    with transaction.atomic():
        job = DocumentProcessingJob.objects.select_for_update().get(pk=job_id)
        job.status = DocumentProcessingJob.STATUS_FAILED
        job.error_message = error_message
        job.completed_at = timezone.now()
        job.source_file_name = source_file_name
        job.save(update_fields=["status", "error_message", "completed_at", "source_file_name"])

        document = job.document
        document.ocr_status = "failed"
        document.save(update_fields=["ocr_status"])

    return DocumentProcessingRunResult(
        job=job,
        status=DocumentProcessingJob.STATUS_FAILED,
        processed=False,
        message=error_message,
        manual_review_required=True,
    )


def _finalize_successful_ocr_job(
    *,
    job_id: int,
    source_file_name: str,
    parsed_payload: dict[str, Any],
    warnings: list[str],
    doc_type_display: str,
) -> DocumentProcessingRunResult:
    with transaction.atomic():
        job = DocumentProcessingJob.objects.select_for_update().get(pk=job_id)
        job.status = DocumentProcessingJob.STATUS_COMPLETED
        job.completed_at = timezone.now()
        job.error_message = ""
        job.source_file_name = source_file_name
        job.save(update_fields=["status", "completed_at", "error_message", "source_file_name"])

        document = job.document
        document.parsed_data = parsed_payload
        document.ocr_status = "success"
        document.ocr_name_mismatch = bool(warnings)
        document.scrub_parsed_pii()
        document.save(update_fields=["parsed_data", "ocr_status", "ocr_name_mismatch"])

    if job.job_type == DocumentProcessingJob.JOB_TYPE_PASSPORT_OCR:
        try:
            from clients.models import MOSApplicationData
            from clients.services.intake_extraction import pre_fill_mos_data_from_ocr
            # OCR of a document must only touch its own case's MOS data.
            mos_data = (
                MOSApplicationData.objects.filter(case=document.case).first()
                if document.case_id
                else None
            )
            if mos_data:
                pre_fill_mos_data_from_ocr(mos_data)
        except Exception as exc:
            logger.warning("Failed to auto-fill mos data from parsed passport: %s", exc)

    msg = (
        _("%(doc_type)s verified with %(warning_count)s warnings.") % {
            "doc_type": doc_type_display,
            "warning_count": len(warnings)
        }
        if warnings else
        _("%(doc_type)s verified successfully.") % {"doc_type": doc_type_display}
    )
    return DocumentProcessingRunResult(
        job=job,
        status=DocumentProcessingJob.STATUS_COMPLETED,
        processed=True,
        message=msg,
        manual_review_required=bool(warnings),
    )


def _finalize_failed_document_job(
    *,
    job_id: int,
    source_file_name: str,
    error_message: str,
) -> DocumentProcessingRunResult:
    with transaction.atomic():
        job = (
            DocumentProcessingJob.objects.select_for_update()
            .select_related("document", "document__client")
            .get(pk=job_id)
        )
        document = Document.objects.select_for_update().select_related("client").get(pk=job.document_id)
        if not _job_matches_processing_state(job, document, source_file_name):
            return DocumentProcessingRunResult(
                job=job,
                status="skipped",
                processed=False,
                message=_("Job was superseded by a newer upload."),
            )

        document.ocr_status = "failed"
        document.ocr_name_mismatch = False
        document.awaiting_confirmation = False
        document.save(update_fields=["ocr_status", "ocr_name_mismatch", "awaiting_confirmation"])

        should_retry = job.attempts < job.max_attempts
        job.status = (
            DocumentProcessingJob.STATUS_PENDING
            if should_retry
            else DocumentProcessingJob.STATUS_FAILED
        )
        job.error_message = error_message
        job.completed_at = timezone.now() if not should_retry else None
        job.lease_expires_at = None
        job.next_attempt_at = (
            timezone.now() + timedelta(minutes=2 ** max(job.attempts - 1, 0))
            if should_retry
            else None
        )
        job.save(
            update_fields=[
                "status",
                "error_message",
                "completed_at",
                "lease_expires_at",
                "next_attempt_at",
            ]
        )

    return DocumentProcessingRunResult(
        job=job,
        status=job.status,
        processed=True,
        message=MANUAL_WEZWANIE_REVIEW_MESSAGE if job.status == DocumentProcessingJob.STATUS_FAILED else _("OCR job requeued for retry."),
        manual_review_required=job.status == DocumentProcessingJob.STATUS_FAILED,
    )


def _finalize_successful_document_job(
    *,
    job_id: int,
    source_file_name: str,
    parsed: WezwanieData,
    send_missing_email: NotificationSender,
    send_appointment_email: NotificationSender,
) -> DocumentProcessingRunResult:
    auto_updates: list[str] = []

    with transaction.atomic():
        job = (
            DocumentProcessingJob.objects.select_for_update()
            .select_related("document", "document__client")
            .get(pk=job_id)
        )
        document = Document.objects.select_for_update().select_related("client").get(pk=job.document_id)
        if not _job_matches_processing_state(job, document, source_file_name):
            return DocumentProcessingRunResult(
                job=job,
                status="skipped",
                processed=False,
                message=_("Job was superseded by a newer upload."),
            )

        client = Client.objects.select_for_update().get(pk=document.client_id)
        actor = job.created_by
        parsed_payload = _build_wezwanie_payload(parsed)

        if job.requires_confirmation:
            document.parsed_data = parsed_payload
            document.ocr_status = "success"
            document.awaiting_confirmation = True
            document.ocr_name_mismatch = _has_name_mismatch(parsed.full_name, client)
            document.save(update_fields=["parsed_data", "ocr_status", "awaiting_confirmation", "ocr_name_mismatch"])
        else:
            case = document.case if document.case_id else None
            case_fields, client_fields, parsed_updates = _apply_parsed_client_updates(
                case,
                client,
                parsed,
                actor=actor,
            )
            auto_updates.extend(parsed_updates)
            _append_required_documents_update(parsed, auto_updates)

            if case is not None and case_fields:
                case.save(update_fields=case_fields)
                log_client_activity(
                    client=client,
                    case=case,
                    actor=actor,
                    event_type="case_updated",
                    summary="Дело обновлено",
                    metadata={"case_id": str(case.uuid), "changed_fields": case_fields},
                    document=document,
                )
            if client_fields:
                client.save(update_fields=client_fields)
                log_client_activity(
                    client=client,
                    case=case,
                    actor=actor,
                    event_type="client_updated",
                    summary="Client name updated from background wezwanie OCR",
                    metadata={"changed_fields": client_fields},
                    document=document,
                )

            document.parsed_data = parsed_payload
            document.ocr_status = "success"
            document.awaiting_confirmation = False
            document.ocr_name_mismatch = _has_name_mismatch(parsed.full_name, client)
            document.scrub_parsed_pii()
            document.save(update_fields=["parsed_data", "ocr_status", "awaiting_confirmation", "ocr_name_mismatch"])

        requires_confirmation = job.requires_confirmation
        job.status = DocumentProcessingJob.STATUS_COMPLETED
        job.error_message = ""
        job.completed_at = timezone.now()
        job.lease_expires_at = None
        job.next_attempt_at = None
        job.save(update_fields=["status", "error_message", "completed_at", "lease_expires_at", "next_attempt_at"])

    if not requires_confirmation:
        auto_updates.extend(
            _send_background_notifications(
                client=client,
                case=job.case,
                parsed=parsed,
                send_missing_email=send_missing_email,
                send_appointment_email=send_appointment_email,
            )
        )

    return DocumentProcessingRunResult(
        job=job,
        status=DocumentProcessingJob.STATUS_COMPLETED,
        processed=True,
        message=_(
            "Queued OCR job completed and awaits confirmation."
            if requires_confirmation
            else "Queued OCR job completed successfully."
        ),
        auto_updates=auto_updates,
    )


def _send_background_notifications(
    *,
    client: Client,
    case: Case | None,
    parsed: WezwanieData,
    send_missing_email: NotificationSender,
    send_appointment_email: NotificationSender,
) -> list[str]:
    auto_updates: list[str] = []

    if _send_notification(send_missing_email, client, "missing-documents email", case=case):
        auto_updates.append(_("missing-documents email sent"))

    if parsed.wezwanie_type == "fingerprints" and parsed.fingerprints_date:
        if _send_notification(send_appointment_email, client, "appointment notification", case=case):
            auto_updates.append(_("appointment notification sent"))

    return auto_updates


def _send_notification(sender: NotificationSender, client: Client, label: str, *, case: Case | None = None) -> bool:
    try:
        if case is not None:
            try:
                return bool(sender(client, case=case))
            except TypeError as exc:
                if "case" not in str(exc):
                    raise
        return bool(sender(client))
    except Exception as exc:
        logger.warning(
            "Failed to send %s for client_id=%s error_type=%s",
            label,
            client.pk,
            type(exc).__name__,
        )
        return False


def _compose_upload_message(
    *,
    document_type_display: str,
    auto_updates: list[str] | None = None,
    manual_review_required: bool = False,
) -> str:
    message = _("Document '%(name)s' uploaded successfully.") % {"name": document_type_display}
    if manual_review_required:
        message = f"{message} {MANUAL_WEZWANIE_REVIEW_MESSAGE}"
    if auto_updates:
        message = message + " " + " ; ".join(auto_updates)
    return message
