from django.shortcuts import render, get_object_or_404, redirect
from django.db import transaction
from django.utils import timezone, translation
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.urls import reverse
from legalize_site.utils.http import request_is_ajax
from legalize_site.utils.files import build_protected_file_response
from django.contrib import messages
from datetime import timedelta
from typing import cast


from clients.forms import DocumentUploadForm
from clients.models import ClientOnboardingSession, ClientDigitalAccess, MOSApplicationData, Client, Document, DocumentRequirement
from clients.services.intake_extraction import pre_fill_mos_data_from_ocr
from clients.services.document_workflow import upload_client_document
from clients.services.access import accessible_clients_queryset
from clients.views.base import role_required_view
from clients.services.onboarding_tokens import generate_onboarding_token, hash_onboarding_token
from clients.use_cases.client_records import finalize_client_creation

EDITABLE_MOS_STATUSES = {"draft", "client_filling", "needs_correction"}
CONTACT_SYNC_FIELDS = ("first_name", "last_name", "phone", "email")


def _mos_data_is_editable(mos_data: MOSApplicationData | None) -> bool:
    return mos_data is None or mos_data.status in EDITABLE_MOS_STATUSES


def _locked_response() -> HttpResponseForbidden:
    return HttpResponseForbidden("This onboarding form is locked for editing.")


def _sync_contact_fields_to_client(client: Client, **values: str) -> None:
    update_fields: list[str] = []
    for field_name in CONTACT_SYNC_FIELDS:
        value = (values.get(field_name) or "").strip()
        if value and getattr(client, field_name) != value:
            setattr(client, field_name, value)
            update_fields.append(field_name)
    if update_fields:
        client.save(update_fields=update_fields)

def check_onboarding_session(token: str) -> ClientOnboardingSession | None:
    token_h = hash_onboarding_token(token)
    session = ClientOnboardingSession.objects.filter(token_hash=token_h, expires_at__gt=timezone.now()).first()
    if not session or session.status not in ["created", "active"]:
        return None
    if session.status == "created":
        session.status = "active"
        session.save(update_fields=["status"])
    # Keep templates backward-compatible: they still reference `session.token_hash` in URLs.
    # We expose the raw token in-memory only (not persisted), so links remain functional
    # while the database stores only hashed values.
    session.token_hash = token
    return session

def onboarding_start(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token)
    if not session:
        return HttpResponseForbidden("Срок действия ссылки истёк или она недействительна.")

    client = session.client
    mos_data = getattr(client, "mos_application_data", None)

    if request.method == "POST":
        if not _mos_data_is_editable(mos_data):
            return _locked_response()
        return redirect("clients:onboarding_digital_access", token=token)

    purpose = client.get_document_requirement_purpose()
    required_docs_catalog = DocumentRequirement.catalog_for(purpose=purpose, language=translation.get_language() or client.language)
    
    existing_docs = Document.objects.filter(client=client).values_list('document_type', 'id')
    existing_map = {doc_type: doc_id for doc_type, doc_id in existing_docs}

    checklist = []
    for item in required_docs_catalog:
        doc_type = item["code"]
        is_uploaded = doc_type in existing_map
        checklist.append({
            "code": doc_type,
            "label": item["label"],
            "is_required": item["is_required"],
            "is_uploaded": is_uploaded,
            "doc_id": existing_map.get(doc_type),
        })

    allow_edit = _mos_data_is_editable(mos_data)
    allow_delete = bool(mos_data and allow_edit)

    status = mos_data.status if mos_data else 'draft'
    if status in ['draft', 'client_filling', 'client_completed', 'needs_correction']:
        case_step = 1
    elif status in ['staff_review']:
        case_step = 2
    elif status in ['approved_by_staff', 'mos_package_ready']:
        case_step = 3
    elif status in ['submitted_in_mos']:
        case_step = 4
    elif status in ['fingerprints']:
        case_step = 5
    elif status in ['waiting_decision', 'decision_received', 'closed']:
        case_step = 6
    else:
        case_step = 1

    return render(request, "clients/onboarding/start.html", {
        "session": session,
        "mos_data": mos_data,
        "checklist": checklist,
        "allow_edit": allow_edit,
        "allow_delete": allow_delete,
        "case_step": case_step,
    })

def onboarding_document_upload(request: HttpRequest, token: str, doc_type: str) -> HttpResponse:
    session = check_onboarding_session(token)
    if not session:
        return HttpResponseForbidden("Invalid or expired onboarding link.")

    mos_data = getattr(session.client, "mos_application_data", None)
    if not _mos_data_is_editable(mos_data):
        return _locked_response()

    if request.method == "POST" and request.FILES.get("file"):
        form = DocumentUploadForm(request.POST, request.FILES, doc_type=doc_type, client=session.client)
        if form.is_valid():
            upload_client_document(
                client=session.client,
                doc_type=doc_type,
                uploaded_document=form.save(commit=False),
                actor=None,
                parse_requested=False,
            )
        else:
            messages.error(request, "File upload failed. Please check the selected file.")
    return redirect("clients:onboarding_start", token=token)


def onboarding_document_preview(request: HttpRequest, token: str, doc_id: int) -> HttpResponse:
    session = check_onboarding_session(token)
    if not session:
        return HttpResponseForbidden("Invalid or expired onboarding link.")

    document = get_object_or_404(Document, id=doc_id, client=session.client)
    return cast(HttpResponse, build_protected_file_response(document.file, as_attachment=False))


def onboarding_document_delete(request: HttpRequest, token: str, doc_id: int) -> HttpResponse:
    session = check_onboarding_session(token)
    if not session:
        return HttpResponseForbidden("Срок действия ссылки истёк или она недействительна.")
        
    client = session.client
    mos_data = getattr(client, "mos_application_data", None)
    
    if not _mos_data_is_editable(mos_data):
        return HttpResponseForbidden("Document changes are locked.")
        
    doc = get_object_or_404(Document, id=doc_id, client=client)
    if not doc.verified:
        doc.delete()
        
    return redirect("clients:onboarding_start", token=token)

def onboarding_digital_access(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token)
    if not session:
        return HttpResponseForbidden("Срок действия ссылки истёк или она недействительна.")

    digital_access, _ = ClientDigitalAccess.objects.get_or_create(client=session.client)

    if request.method == "POST":
        mos_data, created = MOSApplicationData.objects.get_or_create(client=session.client)
        if not _mos_data_is_editable(mos_data):
            return _locked_response()

        digital_access.has_pesel = request.POST.get("has_pesel") == "yes"
        digital_access.has_trusted_profile = request.POST.get("has_trusted_profile") == "yes"
        digital_access.has_mos_account = request.POST.get("has_mos_account") == "yes"
        digital_access.save()

        if created or (not mos_data.passport_data and not mos_data.personal_data):
            pre_fill_mos_data_from_ocr(mos_data)

        return redirect("clients:onboarding_passport", token=token)

    return render(request, "clients/onboarding/digital_access.html", {
        "session": session,
        "digital_access": digital_access,
    })

def onboarding_passport(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token)
    if not session:
        return HttpResponseForbidden("Invalid or expired onboarding link.")

    client = session.client
    mos_data = get_object_or_404(MOSApplicationData, client=client)

    dirty = False
    personal_data = mos_data.personal_data or {}
    for key, val in [
        ("first_name", client.first_name),
        ("last_name", client.last_name),
        ("phone", client.phone),
        ("email", client.email),
        ("citizenship", client.citizenship),
    ]:
        if val and (key not in personal_data or not personal_data[key]):
            personal_data[key] = val
            dirty = True

    if client.birth_date and ("birth_date" not in personal_data or not personal_data["birth_date"]):
        personal_data["birth_date"] = client.birth_date.isoformat()
        dirty = True

    mos_data.personal_data = personal_data

    passport_data = mos_data.passport_data or {}
    if client.passport_num and ("document_number" not in passport_data or not passport_data["document_number"]):
        passport_data["document_number"] = client.passport_num
        dirty = True

    mos_data.passport_data = passport_data

    if dirty:
        mos_data.save()

    if request.method == "POST":
        if not _mos_data_is_editable(mos_data):
            return _locked_response()

        mos_data.status = "client_filling"

        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        phone = request.POST.get("phone", "").strip()
        email = request.POST.get("email", "").strip()
        birth_date_str = request.POST.get("birth_date", "").strip()
        citizenship = request.POST.get("citizenship", "").strip()
        doc_num = request.POST.get("document_number", "").strip()
        expiry_date = request.POST.get("expiry_date", "").strip()
        gender = request.POST.get("gender", "").strip()
        maiden_name = request.POST.get("maiden_name", "").strip()
        previous_surnames = request.POST.get("previous_surnames", "").strip()
        previous_first_names = request.POST.get("previous_first_names", "").strip()
        birth_place = request.POST.get("birth_place", "").strip()
        birth_country = request.POST.get("birth_country", "").strip()
        origin_country = request.POST.get("origin_country", "").strip()

        personal_data = mos_data.personal_data or {}
        personal_data["first_name"] = first_name
        personal_data["last_name"] = last_name
        personal_data["phone"] = phone
        personal_data["email"] = email
        personal_data["birth_date"] = birth_date_str
        personal_data["citizenship"] = citizenship
        personal_data["gender"] = gender
        personal_data["maiden_name"] = maiden_name
        personal_data["previous_surnames"] = previous_surnames
        personal_data["previous_first_names"] = previous_first_names
        personal_data["birth_place"] = birth_place
        personal_data["birth_country"] = birth_country
        personal_data["origin_country"] = origin_country
        mos_data.personal_data = personal_data

        passport_data = mos_data.passport_data or {}
        passport_data["document_number"] = doc_num
        passport_data["expiry_date"] = expiry_date
        passport_data["issue_date"] = request.POST.get("issue_date", "").strip()
        passport_data["issuing_authority"] = request.POST.get("issuing_authority", "").strip()
        mos_data.passport_data = passport_data

        mos_data.save()
        _sync_contact_fields_to_client(
            client,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
        )

        return redirect("clients:onboarding_personal_extra", token=token)

    return render(request, "clients/onboarding/passport.html", {"session": session, "mos_data": mos_data})

def onboarding_personal_extra(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token)
    if not session:
        return HttpResponseForbidden("Срок действия ссылки истёк или она недействительна.")

    mos_data = get_object_or_404(MOSApplicationData, client=session.client)

    if request.method == "POST":
        if not _mos_data_is_editable(mos_data):
            return _locked_response()

        personal_data = mos_data.personal_data or {}
        personal_data["father_name"] = request.POST.get("father_name", "")
        personal_data["mother_name"] = request.POST.get("mother_name", "")
        personal_data["mother_maiden_name"] = request.POST.get("mother_maiden_name", "")
        personal_data["height"] = request.POST.get("height", "")
        personal_data["eye_color"] = request.POST.get("eye_color", "")
        personal_data["education"] = request.POST.get("education", "")
        personal_data["marital_status"] = request.POST.get("marital_status", "")
        personal_data["profession"] = request.POST.get("profession", "").strip()
        personal_data["special_marks"] = request.POST.get("special_marks", "").strip()
        mos_data.personal_data = personal_data
        mos_data.save()
        return redirect("clients:onboarding_address", token=token)

    return render(request, "clients/onboarding/personal_extra.html", {"session": session, "mos_data": mos_data})

def onboarding_address(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token)
    if not session:
        return HttpResponseForbidden("Срок действия ссылки истёк или она недействительна.")

    mos_data = get_object_or_404(MOSApplicationData, client=session.client)

    if request.method == "POST":
        if not _mos_data_is_editable(mos_data):
            return _locked_response()

        address_data = mos_data.address_data or {}
        address_data["street"] = request.POST.get("street", "")
        address_data["city"] = request.POST.get("city", "")
        address_data["postal_code"] = request.POST.get("postal_code", "")
        address_data["meldunek"] = request.POST.get("meldunek") == "yes"
        address_data["home_country"] = request.POST.get("home_country", "")
        address_data["home_city"] = request.POST.get("home_city", "")
        address_data["home_street"] = request.POST.get("home_street", "")
        address_data["voivodeship"] = request.POST.get("voivodeship", "").strip()
        address_data["powiat"] = request.POST.get("powiat", "").strip()
        address_data["gmina"] = request.POST.get("gmina", "").strip()
        address_data["house_number"] = request.POST.get("house_number", "").strip()
        address_data["apartment_number"] = request.POST.get("apartment_number", "").strip()
        mos_data.address_data = address_data
        mos_data.save()
        return redirect("clients:onboarding_travel", token=token)

    return render(request, "clients/onboarding/address.html", {"session": session, "mos_data": mos_data})

def onboarding_travel(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token)
    if not session:
        return HttpResponseForbidden("Срок действия ссылки истёк или она недействительна.")

    mos_data = get_object_or_404(MOSApplicationData, client=session.client)

    if request.method == "POST":
        if not _mos_data_is_editable(mos_data):
            return _locked_response()

        mos_data.mos_purpose = request.POST.get("mos_purpose", "")
        legal_stay_str = request.POST.get("legal_stay_until")
        if legal_stay_str:
            mos_data.legal_stay_until = legal_stay_str
            
        stay_data = mos_data.stay_data or {}
        stay_data["is_in_poland"] = request.POST.get("is_in_poland") == "yes"
        stay_data["last_entry_date"] = request.POST.get("last_entry_date", "")
        stay_data["stay_basis"] = request.POST.get("stay_basis", "")
        stay_data["was_in_poland_before"] = request.POST.get("was_in_poland_before") == "yes"
        stay_data["has_insurance"] = request.POST.get("has_insurance") == "yes"
        stay_data["has_stable_income"] = request.POST.get("has_stable_income") == "yes"
        mos_data.stay_data = stay_data
        
        personal_data = mos_data.personal_data or {}
        personal_data["employer_email"] = request.POST.get("employer_email", "").strip()
        personal_data["university_email"] = request.POST.get("university_email", "").strip()
        mos_data.personal_data = personal_data

        previous_stays_detail = request.POST.get("previous_stays", "").strip()
        mos_data.previous_stays = [previous_stays_detail]
        
        mos_data.travel_history = [request.POST.get("travel_history", "")]
        mos_data.save()
        return redirect("clients:onboarding_declarations", token=token)

    return render(request, "clients/onboarding/travel.html", {"session": session, "mos_data": mos_data})

def onboarding_declarations(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token)
    if not session:
        return HttpResponseForbidden("Срок действия ссылки истёк или она недействительна.")

    mos_data = get_object_or_404(MOSApplicationData, client=session.client)

    if request.method == "POST":
        if not _mos_data_is_editable(mos_data):
            return _locked_response()

        declarations = mos_data.legal_declarations or {}
        declarations["criminal_record"] = request.POST.get("criminal_record") == "yes"
        declarations["tax_arrears"] = request.POST.get("tax_arrears") == "yes"
        mos_data.legal_declarations = declarations
        
        mos_data.status = "client_completed"
        mos_data.client_confirmed_at = timezone.now()
        mos_data.save()
        session.status = "completed"
        session.completed_at = timezone.now()
        session.save(update_fields=["status", "completed_at", "updated_at"])

        # Send notification to staff/manager
        try:
            from clients.services.notifications import send_onboarding_completed_email
            send_onboarding_completed_email(session.client)
        except Exception:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception("Failed to send onboarding completion email")

        return redirect("clients:onboarding_review", token=token)

    return render(request, "clients/onboarding/declarations.html", {"session": session, "mos_data": mos_data})

def onboarding_review(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token)
    if not session:
        return HttpResponseForbidden("Срок действия ссылки истёк или она недействительна.")

    mos_data = get_object_or_404(MOSApplicationData, client=session.client)
    
    return render(request, "clients/onboarding/review.html", {"session": session, "mos_data": mos_data})

@role_required_view("Admin", "Manager", "Staff")
def generate_onboarding_link(request: HttpRequest, client_id: int) -> HttpResponse:
    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), id=client_id)
    token, token_hash = generate_onboarding_token()
    
    payment = client.payments.filter(status__in=["paid", "partial"]).first()
    
    ClientOnboardingSession.objects.create(
        client=client,
        payment=payment,
        token_hash=token_hash,
        status="created",
        expires_at=timezone.now() + timedelta(days=7)
    )
    
    if request_is_ajax(request):
        link = request.build_absolute_uri(
            reverse("clients:onboarding_start", kwargs={"token": token})
        )
        return JsonResponse({
            "status": "ok",
            "link": link,
            "message": "Ссылка на онбординг скопирована!"
        })
    
    messages.success(request, "Ссылка на онбординг успешно создана.")
    return redirect("clients:client_detail", pk=client.id)

def onboarding_personal_data(request: HttpRequest, token: str) -> HttpResponse:
    return redirect("clients:onboarding_passport", token=token)


@role_required_view("Admin", "Manager", "Staff")
def quick_create_client_onboarding(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)
    
    first_name = request.POST.get("first_name", "").strip() or "Новый"
    last_name = request.POST.get("last_name", "").strip() or "Клиент"
    email = request.POST.get("email", "").strip()
    phone = request.POST.get("phone", "").strip()
    language = request.POST.get("language", "pl").strip()
    application_purpose = request.POST.get("application_purpose", "study").strip()

    try:
        with transaction.atomic():
            client = Client.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                citizenship="",
                language=language,
                application_purpose=application_purpose,
                assigned_staff=request.user,
                status="new",
                workflow_stage="new_client",
            )
            finalize_client_creation(
                client=client,
                actor=request.user,
            )
            
            token, token_hash = generate_onboarding_token()
            ClientOnboardingSession.objects.create(
                client=client,
                token_hash=token_hash,
                status="created",
                expires_at=timezone.now() + timedelta(days=7)
            )

        link = request.build_absolute_uri(
            reverse("clients:onboarding_start", kwargs={"token": token})
        )
        return JsonResponse({
            "status": "ok",
            "link": link,
            "message": "Клиент добавлен и ссылка скопирована!"
        })
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


def onboarding_auto_save(request: HttpRequest, token: str) -> HttpResponse:
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    session = check_onboarding_session(token)
    if not session:
        return JsonResponse({"status": "error", "message": "Invalid token"}, status=403)
        
    client = session.client
    mos_data, _ = MOSApplicationData.objects.get_or_create(client=client)
    if not _mos_data_is_editable(mos_data):
        return JsonResponse({"status": "locked", "message": "This onboarding form is locked."}, status=423)
    
    # Process digital access fields if any
    digital_access_updated = False
    if any(k in request.POST for k in ["has_pesel", "has_trusted_profile", "has_mos_account"]):
        digital_access, _ = ClientDigitalAccess.objects.get_or_create(client=client)
        if "has_pesel" in request.POST:
            digital_access.has_pesel = request.POST.get("has_pesel") == "yes"
            digital_access_updated = True
        if "has_trusted_profile" in request.POST:
            digital_access.has_trusted_profile = request.POST.get("has_trusted_profile") == "yes"
            digital_access_updated = True
        if "has_mos_account" in request.POST:
            digital_access.has_mos_account = request.POST.get("has_mos_account") == "yes"
            digital_access_updated = True
        if digital_access_updated:
            digital_access.save()
            
    # Process passport/personal fields (Step 1)
    personal_dirty = False
    passport_dirty = False
    client_dirty = False
    
    personal_data = mos_data.personal_data or {}
    passport_data = mos_data.passport_data or {}
    
    if "first_name" in request.POST:
        val = request.POST.get("first_name", "").strip()
        personal_data["first_name"] = val
        personal_dirty = True
        if val and client.first_name != val:
            client.first_name = val
            client_dirty = True
            
    if "last_name" in request.POST:
        val = request.POST.get("last_name", "").strip()
        personal_data["last_name"] = val
        personal_dirty = True
        if val and client.last_name != val:
            client.last_name = val
            client_dirty = True

    if "phone" in request.POST:
        val = request.POST.get("phone", "").strip()
        personal_data["phone"] = val
        personal_dirty = True
        if val and client.phone != val:
            client.phone = val
            client_dirty = True

    if "email" in request.POST:
        val = request.POST.get("email", "").strip()
        personal_data["email"] = val
        personal_dirty = True
        if val and client.email != val:
            client.email = val
            client_dirty = True
            
    if "birth_date" in request.POST:
        val = request.POST.get("birth_date", "").strip()
        personal_data["birth_date"] = val
        personal_dirty = True
                
    if "citizenship" in request.POST:
        val = request.POST.get("citizenship", "").strip()
        personal_data["citizenship"] = val
        personal_dirty = True
            
    if "document_number" in request.POST:
        val = request.POST.get("document_number", "").strip()
        passport_data["document_number"] = val
        passport_dirty = True
            
    if "expiry_date" in request.POST:
        val = request.POST.get("expiry_date", "").strip()
        passport_data["expiry_date"] = val
        passport_dirty = True

    for field in ["gender", "maiden_name", "previous_surnames", "previous_first_names", "birth_place", "birth_country", "origin_country"]:
        if field in request.POST:
            personal_data[field] = request.POST.get(field, "").strip()
            personal_dirty = True

    for field in ["issue_date", "issuing_authority"]:
        if field in request.POST:
            passport_data[field] = request.POST.get(field, "").strip()
            passport_dirty = True

    # Process personal_extra fields (Step 2 of extra data)
    for field in ["father_name", "mother_name", "mother_maiden_name", "height", "eye_color", "education", "marital_status", "profession", "special_marks"]:
        if field in request.POST:
            personal_data[field] = request.POST.get(field, "")
            personal_dirty = True
            
    if personal_dirty:
        mos_data.personal_data = personal_data
    if passport_dirty:
        mos_data.passport_data = passport_data
        
    # Process address fields
    address_dirty = False
    address_data = mos_data.address_data or {}
    for field in ["street", "city", "postal_code", "home_country", "home_city", "home_street", "voivodeship", "powiat", "gmina", "house_number", "apartment_number"]:
        if field in request.POST:
            address_data[field] = request.POST.get(field, "")
            address_dirty = True
    if "meldunek" in request.POST:
        address_data["meldunek"] = request.POST.get("meldunek") == "yes"
        address_dirty = True
    if address_dirty:
        mos_data.address_data = address_data
        
    # Process travel fields
    if "mos_purpose" in request.POST:
        mos_data.mos_purpose = request.POST.get("mos_purpose", "")
    if "legal_stay_until" in request.POST:
        val = request.POST.get("legal_stay_until", "").strip()
        if val:
            mos_data.legal_stay_until = val
            
    stay_data = mos_data.stay_data or {}
    stay_dirty = False
    if "is_in_poland" in request.POST:
        stay_data["is_in_poland"] = request.POST.get("is_in_poland") == "yes"
        stay_dirty = True
    if "last_entry_date" in request.POST:
        stay_data["last_entry_date"] = request.POST.get("last_entry_date", "")
        stay_dirty = True
    if "stay_basis" in request.POST:
        stay_data["stay_basis"] = request.POST.get("stay_basis", "")
        stay_dirty = True
    if "was_in_poland_before" in request.POST:
        stay_data["was_in_poland_before"] = request.POST.get("was_in_poland_before") == "yes"
        stay_dirty = True
    if "has_insurance" in request.POST:
        stay_data["has_insurance"] = request.POST.get("has_insurance") == "yes"
        stay_dirty = True
    if "has_stable_income" in request.POST:
        stay_data["has_stable_income"] = request.POST.get("has_stable_income") == "yes"
        stay_dirty = True
        
    if stay_dirty:
        mos_data.stay_data = stay_data

    if "employer_email" in request.POST:
        personal_data["employer_email"] = request.POST.get("employer_email", "").strip()
        mos_data.personal_data = personal_data
    if "university_email" in request.POST:
        personal_data["university_email"] = request.POST.get("university_email", "").strip()
        mos_data.personal_data = personal_data
    if "previous_stays" in request.POST:
        mos_data.previous_stays = [request.POST.get("previous_stays", "").strip()]

    if "travel_history" in request.POST:
        mos_data.travel_history = [request.POST.get("travel_history", "")]

    # Process declarations fields
    declarations_dirty = False
    declarations = mos_data.legal_declarations or {}
    if "criminal_record" in request.POST:
        declarations["criminal_record"] = request.POST.get("criminal_record") == "yes"
        declarations_dirty = True
    if "tax_arrears" in request.POST:
        declarations["tax_arrears"] = request.POST.get("tax_arrears") == "yes"
        declarations_dirty = True
    if declarations_dirty:
        mos_data.legal_declarations = declarations

    # Set status to client_filling if not already filled or completed
    if mos_data.status not in ["client_completed", "staff_review", "approved_by_staff", "mos_package_ready", "submitted_in_mos", "fingerprints", "waiting_decision", "decision_received", "closed"]:
        mos_data.status = "client_filling"

    mos_data.save()
    if client_dirty:
        client.save()
        
    return JsonResponse({"status": "ok", "message": "Draft auto-saved"})
