from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone, translation
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from legalize_site.utils.http import request_is_ajax
from django.contrib import messages
import uuid
from datetime import timedelta
from clients.models import ClientOnboardingSession, ClientDigitalAccess, MOSApplicationData, Client, ClientFamilyMemberMOS, Document, DocumentRequirement
from clients.services.intake_extraction import pre_fill_mos_data_from_ocr

def check_onboarding_session(token: str) -> ClientOnboardingSession | None:
    session = ClientOnboardingSession.objects.filter(token_hash=token, expires_at__gt=timezone.now()).first()
    if not session or session.status not in ["created", "active"]:
        return None
    if session.status == "created":
        session.status = "active"
        session.save(update_fields=["status"])
    return session

def onboarding_start(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token)
    if not session:
        return HttpResponseForbidden("Срок действия ссылки истёк или она недействительна.")

    client = session.client
    mos_data = getattr(client, "mos_application_data", None)

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

    locked_statuses = ['client_completed', 'staff_review', 'approved_by_staff', 'mos_package_ready', 'submitted_in_mos', 'fingerprints', 'waiting_decision', 'decision_received', 'closed']
    allow_delete = mos_data and mos_data.status not in locked_statuses

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
        "allow_delete": allow_delete,
        "case_step": case_step,
    })

def onboarding_document_upload(request: HttpRequest, token: str, doc_type: str) -> HttpResponse:
    session = check_onboarding_session(token)
    if not session:
        return HttpResponseForbidden("Срок действия ссылки истёк или она недействительна.")
        
    if request.method == "POST" and request.FILES.get("file"):
        Document.objects.create(
            client=session.client,
            document_type=doc_type,
            file=request.FILES["file"]
        )
    return redirect("clients:onboarding_start", token=token)

def onboarding_document_delete(request: HttpRequest, token: str, doc_id: int) -> HttpResponse:
    session = check_onboarding_session(token)
    if not session:
        return HttpResponseForbidden("Срок действия ссылки истёк или она недействительна.")
        
    client = session.client
    mos_data = getattr(client, "mos_application_data", None)
    
    locked_statuses = ['client_completed', 'staff_review', 'approved_by_staff', 'mos_package_ready', 'submitted_in_mos', 'fingerprints', 'waiting_decision', 'decision_received', 'closed']
    if mos_data and mos_data.status in locked_statuses:
        return HttpResponseForbidden("Удаление заблокировано.")
        
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
        digital_access.has_pesel = request.POST.get("has_pesel") == "yes"
        digital_access.has_trusted_profile = request.POST.get("has_trusted_profile") == "yes"
        digital_access.has_mos_account = request.POST.get("has_mos_account") == "yes"
        digital_access.save()
        
        mos_data, created = MOSApplicationData.objects.get_or_create(client=session.client)
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
        return HttpResponseForbidden("Срок действия ссылки истёк или она недействительна.")

    client = session.client
    mos_data = get_object_or_404(MOSApplicationData, client=client)

    # Pre-fill mos_data fields if they are blank and available in client
    dirty = False
    personal_data = mos_data.personal_data or {}
    for key, val in [
        ("first_name", client.first_name),
        ("last_name", client.last_name),
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
        mos_data.status = "client_filling"
        
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        birth_date_str = request.POST.get("birth_date", "").strip()
        citizenship = request.POST.get("citizenship", "").strip()
        doc_num = request.POST.get("document_number", "").strip()
        expiry_date = request.POST.get("expiry_date", "").strip()

        personal_data = mos_data.personal_data or {}
        personal_data["first_name"] = first_name
        personal_data["last_name"] = last_name
        personal_data["birth_date"] = birth_date_str
        personal_data["citizenship"] = citizenship
        mos_data.personal_data = personal_data

        passport_data = mos_data.passport_data or {}
        passport_data["document_number"] = doc_num
        passport_data["expiry_date"] = expiry_date
        mos_data.passport_data = passport_data

        mos_data.save()

        # Update Client model fields in real-time
        client_dirty = False
        if first_name and client.first_name != first_name:
            client.first_name = first_name
            client_dirty = True
        if last_name and client.last_name != last_name:
            client.last_name = last_name
            client_dirty = True
        if citizenship and client.citizenship != citizenship:
            client.citizenship = citizenship
            client_dirty = True
        if doc_num and client.passport_num != doc_num:
            client.passport_num = doc_num
            client_dirty = True
        if birth_date_str:
            from django.utils.dateparse import parse_date
            parsed_birth = parse_date(birth_date_str)
            if parsed_birth and client.birth_date != parsed_birth:
                client.birth_date = parsed_birth
                client_dirty = True
        if client_dirty:
            client.save()

        return redirect("clients:onboarding_personal_extra", token=token)

    return render(request, "clients/onboarding/passport.html", {"session": session, "mos_data": mos_data})

def onboarding_personal_extra(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token)
    if not session:
        return HttpResponseForbidden("Срок действия ссылки истёк или она недействительна.")

    mos_data = get_object_or_404(MOSApplicationData, client=session.client)

    if request.method == "POST":
        personal_data = mos_data.personal_data or {}
        personal_data["father_name"] = request.POST.get("father_name", "")
        personal_data["mother_name"] = request.POST.get("mother_name", "")
        personal_data["mother_maiden_name"] = request.POST.get("mother_maiden_name", "")
        personal_data["height"] = request.POST.get("height", "")
        personal_data["eye_color"] = request.POST.get("eye_color", "")
        personal_data["education"] = request.POST.get("education", "")
        personal_data["marital_status"] = request.POST.get("marital_status", "")
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
        address_data = mos_data.address_data or {}
        address_data["street"] = request.POST.get("street", "")
        address_data["city"] = request.POST.get("city", "")
        address_data["postal_code"] = request.POST.get("postal_code", "")
        address_data["meldunek"] = request.POST.get("meldunek") == "yes"
        address_data["home_country"] = request.POST.get("home_country", "")
        address_data["home_city"] = request.POST.get("home_city", "")
        address_data["home_street"] = request.POST.get("home_street", "")
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
        mos_data.mos_purpose = request.POST.get("mos_purpose", "")
        legal_stay_str = request.POST.get("legal_stay_until")
        if legal_stay_str:
            mos_data.legal_stay_until = legal_stay_str
            
        stay_data = mos_data.stay_data or {}
        stay_data["is_in_poland"] = request.POST.get("is_in_poland") == "yes"
        stay_data["last_entry_date"] = request.POST.get("last_entry_date", "")
        stay_data["stay_basis"] = request.POST.get("stay_basis", "")
        stay_data["was_in_poland_before"] = request.POST.get("was_in_poland_before") == "yes"
        mos_data.stay_data = stay_data
        
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
        declarations = mos_data.legal_declarations or {}
        declarations["criminal_record"] = request.POST.get("criminal_record") == "yes"
        declarations["tax_arrears"] = request.POST.get("tax_arrears") == "yes"
        mos_data.legal_declarations = declarations
        
        mos_data.status = "client_completed"
        mos_data.client_confirmed_at = timezone.now()
        mos_data.save()

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

@login_required
def generate_onboarding_link(request: HttpRequest, client_id: int) -> HttpResponse:
    client = get_object_or_404(Client, id=client_id)
    token = uuid.uuid4().hex
    
    payment = client.payments.filter(status__in=["paid", "partial"]).first()
    
    session = ClientOnboardingSession.objects.create(
        client=client,
        payment=payment,
        token_hash=token,
        status="created",
        expires_at=timezone.now() + timedelta(days=7)
    )
    
    if request_is_ajax(request):
        link = request.build_absolute_uri(
            reverse("clients:onboarding_start", kwargs={"token": session.token_hash})
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


from django.db import transaction
from clients.views.base import role_required_view
from clients.use_cases.client_records import finalize_client_creation

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
            
            token = uuid.uuid4().hex
            session = ClientOnboardingSession.objects.create(
                client=client,
                token_hash=token,
                status="created",
                expires_at=timezone.now() + timedelta(days=7)
            )

        link = request.build_absolute_uri(
            reverse("clients:onboarding_start", kwargs={"token": session.token_hash})
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
