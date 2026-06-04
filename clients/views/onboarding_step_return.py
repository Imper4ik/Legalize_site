from __future__ import annotations

from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from clients.models import ClientDigitalAccess, MOSApplicationData
from clients.security.encrypted import safe_encrypted_attr
from clients.services.onboarding_purposes import normalize_onboarding_purpose
from clients.services.onboarding_reminders import clear_onboarding_notifications_cache
from clients.views import onboarding_views


def _auth_redirect(request: HttpRequest, session, token: str) -> HttpResponse | None:
    return onboarding_views.check_client_auth(request, session, token)


def _save_return_requested(request: HttpRequest) -> bool:
    return request.POST.get("action") == "save_return"


def _next_or_dashboard(request: HttpRequest, token: str, next_view_name: str) -> HttpResponse:
    if _save_return_requested(request):
        return redirect("clients:onboarding_start", token=token)
    return redirect(next_view_name, token=token)


def onboarding_digital_access(request: HttpRequest, token: str) -> HttpResponse:
    session = onboarding_views.check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))
    auth_redirect = _auth_redirect(request, session, token)
    if auth_redirect:
        return auth_redirect

    mos_data, created = MOSApplicationData.objects.get_or_create(client=session.client)
    if not onboarding_views._mos_data_is_editable(mos_data):
        return onboarding_views._locked_response(request, session)

    digital_access, created_access = ClientDigitalAccess.objects.defer("pesel").get_or_create(client=session.client)

    if request.method == "POST":
        digital_access.has_pesel = request.POST.get("has_pesel") == "yes"
        digital_access.has_trusted_profile = request.POST.get("has_trusted_profile") == "yes"
        digital_access.has_mos_account = request.POST.get("has_mos_account") == "yes"
        digital_access.save()

        if created or (not mos_data.passport_data and not mos_data.personal_data):
            onboarding_views.pre_fill_mos_data_from_ocr(mos_data)

        return _next_or_dashboard(request, token, "clients:onboarding_passport")

    return render(request, "clients/onboarding/digital_access.html", {
        "session": session,
        "digital_access": digital_access,
    })


def onboarding_passport(request: HttpRequest, token: str) -> HttpResponse:
    session = onboarding_views.check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Invalid or expired onboarding link."))
    auth_redirect = _auth_redirect(request, session, token)
    if auth_redirect:
        return auth_redirect

    client = session.client
    mos_data = get_object_or_404(MOSApplicationData, client=client)

    if not onboarding_views._mos_data_is_editable(mos_data):
        return onboarding_views._locked_response(request, session)

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
    passport_num = safe_encrypted_attr(client, "passport_num")
    if passport_num and ("document_number" not in passport_data or not passport_data["document_number"]):
        passport_data["document_number"] = passport_num
        dirty = True

    mos_data.passport_data = passport_data

    if dirty:
        mos_data.save()

    if request.method == "POST":
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
        onboarding_views._sync_contact_fields_to_client(
            client,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
        )

        return _next_or_dashboard(request, token, "clients:onboarding_personal_extra")

    return render(request, "clients/onboarding/passport.html", {"session": session, "mos_data": mos_data})


def onboarding_personal_extra(request: HttpRequest, token: str) -> HttpResponse:
    session = onboarding_views.check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))
    auth_redirect = _auth_redirect(request, session, token)
    if auth_redirect:
        return auth_redirect

    mos_data = get_object_or_404(MOSApplicationData, client=session.client)

    if not onboarding_views._mos_data_is_editable(mos_data):
        return onboarding_views._locked_response(request, session)

    if request.method == "POST":
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
        return _next_or_dashboard(request, token, "clients:onboarding_address")

    return render(request, "clients/onboarding/personal_extra.html", {"session": session, "mos_data": mos_data})


def onboarding_address(request: HttpRequest, token: str) -> HttpResponse:
    session = onboarding_views.check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))
    auth_redirect = _auth_redirect(request, session, token)
    if auth_redirect:
        return auth_redirect

    mos_data = get_object_or_404(MOSApplicationData, client=session.client)

    if not onboarding_views._mos_data_is_editable(mos_data):
        return onboarding_views._locked_response(request, session)

    if request.method == "POST":
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
        return _next_or_dashboard(request, token, "clients:onboarding_travel")

    return render(request, "clients/onboarding/address.html", {"session": session, "mos_data": mos_data})


def onboarding_travel(request: HttpRequest, token: str) -> HttpResponse:
    session = onboarding_views.check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))
    auth_redirect = _auth_redirect(request, session, token)
    if auth_redirect:
        return auth_redirect

    mos_data = get_object_or_404(MOSApplicationData, client=session.client)

    if not onboarding_views._mos_data_is_editable(mos_data):
        return onboarding_views._locked_response(request, session)

    if request.method == "POST":
        purpose_updated = False

        if "mos_purpose" in request.POST:
            try:
                selected_purpose = normalize_onboarding_purpose(request.POST.get("mos_purpose"))
            except ValueError:
                return HttpResponseBadRequest(_("Invalid application purpose."))
            if mos_data.mos_purpose != selected_purpose:
                mos_data.mos_purpose = selected_purpose
                purpose_updated = True
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
        if purpose_updated:
            clear_onboarding_notifications_cache(session.client)
        return _next_or_dashboard(request, token, "clients:onboarding_declarations")

    return render(request, "clients/onboarding/travel.html", {
        "session": session,
        "mos_data": mos_data,
        "can_change_purpose": True,
        **onboarding_views._purpose_context(session.client, mos_data),
    })


def onboarding_declarations(request: HttpRequest, token: str) -> HttpResponse:
    session = onboarding_views.check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))
    auth_redirect = _auth_redirect(request, session, token)
    if auth_redirect:
        return auth_redirect

    mos_data = get_object_or_404(MOSApplicationData, client=session.client)

    if not onboarding_views._mos_data_is_editable(mos_data):
        return onboarding_views._locked_response(request, session)

    if request.method == "POST":
        declarations = mos_data.legal_declarations or {}
        declarations["criminal_record"] = request.POST.get("criminal_record") == "yes"
        declarations["tax_arrears"] = request.POST.get("tax_arrears") == "yes"
        mos_data.legal_declarations = declarations

        if _save_return_requested(request):
            if mos_data.status == "draft":
                mos_data.status = "client_filling"
            mos_data.save()
            return redirect("clients:onboarding_start", token=token)

        mos_data.status = "client_completed"
        mos_data.client_confirmed_at = timezone.now()
        mos_data.save()
        session.status = "completed"
        session.completed_at = timezone.now()
        session.save(update_fields=["status", "completed_at", "updated_at"])

        try:
            from clients.services.notifications import send_onboarding_completed_email
            send_onboarding_completed_email(session.client)
        except Exception:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception("Failed to send onboarding completion email")

        return redirect("clients:onboarding_review", token=token)

    return render(request, "clients/onboarding/declarations.html", {"session": session, "mos_data": mos_data})
