from typing import Any
from clients.models import Client, MOSApplicationData

def pre_fill_mos_data_from_ocr(mos_data: MOSApplicationData) -> bool:
    """
    Attempts to pre-fill MOSApplicationData fields based on parsed_data 
    from the client's documents (e.g., passport) if they are currently empty.
    Returns True if any data was updated.
    """
    updated = False
    client = mos_data.client

    # Pre-fill Passport & Personal Data
    if not mos_data.passport_data and not mos_data.personal_data:
        # Find a completed passport document
        passport_doc = client.documents.filter(
            document_type="passport",
            ocr_status="success",
            parsed_data__isnull=False
        ).first()

        if passport_doc and passport_doc.parsed_data:
            parsed = passport_doc.parsed_data
            
            personal_data = {}
            if "first_name" in parsed:
                personal_data["first_name"] = parsed["first_name"]
            if "last_name" in parsed:
                personal_data["last_name"] = parsed["last_name"]
            
            passport_data = {}
            if "document_number" in parsed or "passport_number" in parsed:
                passport_data["document_number"] = parsed.get("passport_number") or parsed.get("document_number")
            if "expiry_date" in parsed:
                passport_data["expiry_date"] = parsed["expiry_date"]

            if personal_data:
                mos_data.personal_data = personal_data
                updated = True
            if passport_data:
                mos_data.passport_data = passport_data
                updated = True

    # Similarly, we can look for "meldunek" for address_data etc.

    if updated:
        mos_data.save(update_fields=["personal_data", "passport_data", "updated_at"])
    
    return updated
