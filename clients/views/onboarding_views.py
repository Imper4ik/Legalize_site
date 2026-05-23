from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import uuid
from datetime import timedelta
from clients.models import ClientOnboardingSession, ClientDigitalAccess, MOSApplicationData, Client, ClientFamilyMemberMOS
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

    if request.method == "POST":
        return redirect("clients:onboarding_digital_access", token=token)

    return render(request, "clients/onboarding/start.html", {"session": session})

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

    mos_data = get_object_or_404(MOSApplicationData, client=session.client)

    if request.method == "POST":
        mos_data.status = "client_filling"
        
        personal_data = mos_data.personal_data or {}
        personal_data["first_name"] = request.POST.get("first_name", "")
        personal_data["last_name"] = request.POST.get("last_name", "")
        personal_data["birth_date"] = request.POST.get("birth_date", "")
        personal_data["citizenship"] = request.POST.get("citizenship", "")
        mos_data.personal_data = personal_data

        passport_data = mos_data.passport_data or {}
        passport_data["document_number"] = request.POST.get("document_number", "")
        passport_data["expiry_date"] = request.POST.get("expiry_date", "")
        mos_data.passport_data = passport_data

        mos_data.save()
        return redirect("clients:onboarding_address", token=token)

    return render(request, "clients/onboarding/passport.html", {"session": session, "mos_data": mos_data})

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
        mos_data.address_data = address_data
        mos_data.save()
        return redirect("clients:onboarding_family_purpose", token=token)

    return render(request, "clients/onboarding/address.html", {"session": session, "mos_data": mos_data})

def onboarding_family_purpose(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token)
    if not session:
        return HttpResponseForbidden("Срок действия ссылки истёк или она недействительна.")

    mos_data = get_object_or_404(MOSApplicationData, client=session.client)

    if request.method == "POST":
        mos_data.mos_purpose = request.POST.get("mos_purpose", "")
        legal_stay_str = request.POST.get("legal_stay_until")
        if legal_stay_str:
            mos_data.legal_stay_until = legal_stay_str
        mos_data.save()
        return redirect("clients:onboarding_finances", token=token)

    return render(request, "clients/onboarding/family_purpose.html", {"session": session, "mos_data": mos_data})

def onboarding_finances(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token)
    if not session:
        return HttpResponseForbidden("Срок действия ссылки истёк или она недействительна.")

    mos_data = get_object_or_404(MOSApplicationData, client=session.client)

    if request.method == "POST":
        finances = mos_data.financial_data or {}
        finances["has_income"] = request.POST.get("has_income") == "yes"
        finances["income_source"] = request.POST.get("income_source", "")
        
        insurance = mos_data.insurance_data or {}
        insurance["has_zus"] = request.POST.get("has_zus") == "yes"
        insurance["has_private"] = request.POST.get("has_private") == "yes"
        
        mos_data.financial_data = finances
        mos_data.insurance_data = insurance
        mos_data.save()
        return redirect("clients:onboarding_declarations", token=token)

    return render(request, "clients/onboarding/finances.html", {"session": session, "mos_data": mos_data})

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
    
    ClientOnboardingSession.objects.create(
        client=client,
        payment=payment,
        token_hash=token,
        status="created",
        expires_at=timezone.now() + timedelta(days=7)
    )
    
    messages.success(request, "Ссылка на онбординг успешно создана.")
    return redirect("clients:client_detail", pk=client.id)

def onboarding_personal_data(request: HttpRequest, token: str) -> HttpResponse:
    return redirect("clients:onboarding_passport", token=token)
