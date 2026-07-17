from typing import Any

from clients.models import MOSApplicationData
from clients.security.encrypted import require_encrypted_json_dict


def pre_fill_mos_data_from_ocr(mos_data: MOSApplicationData) -> bool:
    """
    Attempts to pre-fill MOSApplicationData fields based on parsed_data
    from the client's documents (e.g., passport) if they are currently empty.
    Returns True if any data was updated.
    """
    updated = False
    client = mos_data.client

    # Find a completed passport document
    passport_doc = (
        client.documents.filter(
            case=mos_data.case,
            document_type="passport",
            ocr_status="success",
            parsed_data__isnull=False,
        )
        .order_by("-uploaded_at", "-pk")
        .first()
    )

    if passport_doc:
        parsed = require_encrypted_json_dict(passport_doc, "parsed_data")
        if not parsed:
            return False

        personal_data: dict[str, Any] = require_encrypted_json_dict(mos_data, "personal_data")
        passport_data: dict[str, Any] = require_encrypted_json_dict(mos_data, "passport_data")

        # Fill missing personal data fields if empty
        if "first_name" in parsed and parsed["first_name"]:
            if not personal_data.get("first_name"):
                personal_data["first_name"] = parsed["first_name"]
                updated = True
        if "last_name" in parsed and parsed["last_name"]:
            if not personal_data.get("last_name"):
                personal_data["last_name"] = parsed["last_name"]
                updated = True
        if "date_of_birth" in parsed and parsed["date_of_birth"]:
            if not personal_data.get("birth_date"):
                personal_data["birth_date"] = parsed["date_of_birth"]
                updated = True
        if "country" in parsed and parsed["country"]:
            if not personal_data.get("citizenship"):
                personal_data["citizenship"] = parsed["country"]
                updated = True

        # Fill missing passport data fields if empty
        passport_number = parsed.get("passport_number") or parsed.get("document_number")
        if passport_number:
            if not passport_data.get("document_number"):
                passport_data["document_number"] = passport_number
                updated = True
        if "valid_until" in parsed and parsed["valid_until"]:
            if not passport_data.get("expiry_date"):
                passport_data["expiry_date"] = parsed["valid_until"]
                updated = True

        if updated:
            mos_data.personal_data = personal_data  # type: ignore[assignment]
            mos_data.passport_data = passport_data  # type: ignore[assignment]
            mos_data.save(update_fields=["personal_data", "passport_data", "updated_at"])

    return updated
