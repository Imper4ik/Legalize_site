from __future__ import annotations

from typing import Any, cast

from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from clients.models import ClientDigitalAccess, ClientOnboardingSession, MOSApplicationData
from clients.security.encrypted import safe_encrypted_attr
from clients.services.intake_extraction import pre_fill_mos_data_from_ocr
from clients.services.onboarding_purposes import clear_onboarding_notifications_cache, normalize_onboarding_purpose
from clients.views import onboarding_views


def _auth_redirect(request: HttpRequest, session: ClientOnboardingSession, token: str) -> HttpResponse | None:
    return onboarding_views.check_client_auth_token_link(request, session, token)


def _scoped_mos_get_or_404(session: ClientOnboardingSession) -> MOSApplicationData:
    """Fetch the MOS record for the session's active case (spec section 1).

    A multi-case client must only ever read/write the MOS of the case in scope,
    never an arbitrary ``.first()`` record.
    """
    return get_object_or_404(
        MOSApplicationData,
        client=session.client,
        case=onboarding_views._session_case(session),
    )


def _scoped_mos_or_new(session: ClientOnboardingSession) -> MOSApplicationData:
    case = onboarding_views._session_case(session)
    mos = MOSApplicationData.objects.filter(client=session.client, case=case).first()
    return mos if mos is not None else MOSApplicationData(client=session.client, case=case)


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
    case_redirect = onboarding_views._require_portal_case(request, session, token)
    if case_redirect:
        return case_redirect

    mos_data = _scoped_mos_or_new(session)

    if mos_data.pk and not onboarding_views._mos_data_is_editable(mos_data):
        return onboarding_views._locked_response(request, session)

    try:
        digital_access = ClientDigitalAccess.objects.defer("pesel").get(client=session.client)
    except ClientDigitalAccess.DoesNotExist:
        digital_access = ClientDigitalAccess(client=session.client)

    if request.method == "POST":
        mos_data, created = onboarding_views._ensure_mos(session.client, onboarding_views._session_case(session))
        digital_access, created_access = ClientDigitalAccess.objects.get_or_create(client=session.client)

        digital_access.has_pesel = request.POST.get("has_pesel") == "yes"
        digital_access.has_trusted_profile = request.POST.get("has_trusted_profile") == "yes"
        digital_access.has_mos_account = request.POST.get("has_mos_account") == "yes"
        digital_access.save()

        if created or (not mos_data.passport_data and not mos_data.personal_data):
            pre_fill_mos_data_from_ocr(mos_data)

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
    case_redirect = onboarding_views._require_portal_case(request, session, token)
    if case_redirect:
        return case_redirect

    client = session.client
    mos_data = _scoped_mos_or_new(session)

    if mos_data.pk and not onboarding_views._mos_data_is_editable(mos_data):
        return onboarding_views._locked_response(request, session)

    # Prefill in-memory only (without saving) for rendering form.
    # EncryptedJSONField stores dicts but django-stubs types it as text.
    personal_data = dict(cast("dict[str, Any]", mos_data.personal_data) or {})
    for key, val in [
        ("first_name", client.first_name),
        ("last_name", client.last_name),
        ("phone", client.phone),
        ("email", client.email),
        ("citizenship", client.citizenship),
    ]:
        if val and (key not in personal_data or not personal_data[key]):
            personal_data[key] = val

    if client.birth_date and ("birth_date" not in personal_data or not personal_data["birth_date"]):
        personal_data["birth_date"] = client.birth_date.isoformat()

    mos_data.personal_data = personal_data

    passport_data = dict(cast("dict[str, Any]", mos_data.passport_data) or {})
    passport_num_val = safe_encrypted_attr(client, "passport_num")
    if passport_num_val and ("document_number" not in passport_data or not passport_data["document_number"]):
        passport_data["document_number"] = passport_num_val
    mos_data.passport_data = passport_data

    if request.method == "POST":
        # Ensure mos_data is saved to DB
        mos_data, _created = onboarding_views._ensure_mos(client, onboarding_views._session_case(session))
        action = request.POST.get("action", "")
        if action == "upload_passport" or request.FILES.get("passport_file"):
            passport_file = request.FILES.get("passport_file")
            if passport_file:
                from django.contrib import messages

                from clients.forms import DocumentUploadForm
                from clients.services.document_workflow import upload_client_document

                # Copy request.FILES to map passport_file to file for the form validation
                files_dict = request.FILES.copy()
                files_dict["file"] = passport_file

                form = DocumentUploadForm(request.POST, files_dict, doc_type="passport", client=client)
                if form.is_valid():
                    upload_client_document(
                        client=client,
                        doc_type="passport",
                        uploaded_document=form.save(commit=False),
                        actor=request.user if request.user.is_authenticated else None,
                        parse_requested=True,
                        case=onboarding_views._session_case(session),
                    )
                    messages.success(request, _("Скан паспорта успешно загружен. Данные распознаются."))
                else:
                    error_text = " ".join(str(error) for errors in form.errors.values() for error in errors)
                    messages.error(request, _("Не удалось загрузить файл: %(errors)s") % {"errors": error_text})
            else:
                from django.contrib import messages
                messages.error(request, _("Выберите файл для загрузки."))
            return redirect("clients:onboarding_passport", token=token)

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

        personal_data = cast("dict[str, Any]", mos_data.personal_data) or {}
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

        passport_data = cast("dict[str, Any]", mos_data.passport_data) or {}
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

    passport_doc = (
        client.documents.filter(
            document_type="passport", case=onboarding_views._session_case(session)
        )
        .order_by("-uploaded_at")
        .first()
    )
    return render(
        request,
        "clients/onboarding/passport.html",
        {
            "session": session,
            "mos_data": mos_data,
            "passport_doc": passport_doc,
        },
    )


def onboarding_personal_extra(request: HttpRequest, token: str) -> HttpResponse:
    session = onboarding_views.check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))
    auth_redirect = _auth_redirect(request, session, token)
    if auth_redirect:
        return auth_redirect
    case_redirect = onboarding_views._require_portal_case(request, session, token)
    if case_redirect:
        return case_redirect

    mos_data = _scoped_mos_get_or_404(session)

    if not onboarding_views._mos_data_is_editable(mos_data):
        return onboarding_views._locked_response(request, session)

    if request.method == "POST":
        personal_data = cast("dict[str, Any]", mos_data.personal_data) or {}
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
    case_redirect = onboarding_views._require_portal_case(request, session, token)
    if case_redirect:
        return case_redirect

    mos_data = _scoped_mos_get_or_404(session)

    if not onboarding_views._mos_data_is_editable(mos_data):
        return onboarding_views._locked_response(request, session)

    if request.method == "POST":
        address_data = cast("dict[str, Any]", mos_data.address_data) or {}
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
    case_redirect = onboarding_views._require_portal_case(request, session, token)
    if case_redirect:
        return case_redirect

    mos_data = _scoped_mos_get_or_404(session)

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
        legal_stay_str = request.POST.get("legal_stay_until", "").strip()
        if legal_stay_str:
            from django.utils.dateparse import parse_date
            parsed_date = parse_date(legal_stay_str)
            if parsed_date:
                mos_data.legal_stay_until = parsed_date
            else:
                return HttpResponseBadRequest(_("Invalid date format for legal stay. Expected YYYY-MM-DD."))
        else:
            mos_data.legal_stay_until = None

        stay_data = cast("dict[str, Any]", mos_data.stay_data) or {}
        stay_data["is_in_poland"] = request.POST.get("is_in_poland") == "yes"
        stay_data["last_entry_date"] = request.POST.get("last_entry_date", "")
        stay_data["stay_basis"] = request.POST.get("stay_basis", "")
        stay_data["was_in_poland_before"] = request.POST.get("was_in_poland_before") == "yes"
        stay_data["has_insurance"] = request.POST.get("has_insurance") == "yes"
        stay_data["has_stable_income"] = request.POST.get("has_stable_income") == "yes"
        mos_data.stay_data = stay_data

        personal_data = cast("dict[str, Any]", mos_data.personal_data) or {}
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
    case_redirect = onboarding_views._require_portal_case(request, session, token)
    if case_redirect:
        return case_redirect

    mos_data = _scoped_mos_get_or_404(session)

    if not onboarding_views._mos_data_is_editable(mos_data):
        return onboarding_views._locked_response(request, session)

    if request.method == "POST":
        declarations = cast("dict[str, Any]", mos_data.legal_declarations) or {}
        declarations["criminal_record"] = request.POST.get("criminal_record") == "yes"
        declarations["tax_arrears"] = request.POST.get("tax_arrears") == "yes"
        mos_data.legal_declarations = declarations

        if _save_return_requested(request):
            if mos_data.status == "draft":
                mos_data.status = "client_filling"
            mos_data.save()
            return redirect("clients:onboarding_start", token=token)

        # RODO: completing the questionnaire requires the subject to accept the
        # data-processing consent. Do not finalise without it.
        from clients.models import AppSettings, ConsentRecord
        from clients.services.consent import record_onboarding_consent

        consent_given = request.POST.get("rodo_consent") == "on" or ConsentRecord.is_granted(
            session.client, ConsentRecord.Purpose.DATA_PROCESSING
        )
        if not consent_given:
            from django.contrib import messages

            messages.error(
                request,
                _("Чтобы завершить анкету, необходимо согласие на обработку персональных данных."),
            )
            return render(
                request,
                "clients/onboarding/declarations.html",
                {
                    "session": session,
                    "mos_data": mos_data,
                    "consent_error": True,
                    "app_settings": AppSettings.get_solo(),
                    "consent_already_given": False,
                },
            )

        record_onboarding_consent(client=session.client, case=mos_data.case, request=request)

        mos_data.status = "client_completed"
        mos_data.client_confirmed_at = timezone.now()
        mos_data.save()
        session.status = "completed"
        session.completed_at = timezone.now()
        session.save(update_fields=["status", "completed_at", "updated_at"])

        try:
            from clients.services.notifications import send_onboarding_completed_email
            send_onboarding_completed_email(session.client, case=mos_data.case)
        except Exception:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception("Failed to send onboarding completion email")

        return redirect("clients:onboarding_review", token=token)

    from clients.models import AppSettings, ConsentRecord

    return render(
        request,
        "clients/onboarding/declarations.html",
        {
            "session": session,
            "mos_data": mos_data,
            "app_settings": AppSettings.get_solo(),
            "consent_already_given": ConsentRecord.is_granted(
                session.client, ConsentRecord.Purpose.DATA_PROCESSING
            ),
        },
    )


def onboarding_consent(request: HttpRequest, token: str) -> HttpResponse:
    """Subject-facing consent centre: view current consents, grant or withdraw.

    Implements art. 7(3) RODO — withdrawing consent is as easy as giving it.
    Each action appends an immutable row to the consent log.
    """
    from django.contrib import messages

    from clients.models import AppSettings, ConsentRecord
    from clients.services.consent import current_policy_version

    session = onboarding_views.check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))
    auth_redirect = _auth_redirect(request, session, token)
    if auth_redirect:
        return auth_redirect

    client = session.client
    valid_purposes = {choice for choice, _label in ConsentRecord.Purpose.choices}

    if request.method == "POST":
        purpose = request.POST.get("purpose", "")
        action = request.POST.get("action", "")
        if purpose not in valid_purposes or action not in {"grant", "withdraw"}:
            return HttpResponseBadRequest(_("Некорректный запрос."))
        granted = action == "grant"
        # Only append a row when the decision actually changes.
        if ConsentRecord.is_granted(client, purpose) != granted:
            ConsentRecord.record(
                client=client,
                purpose=purpose,
                granted=granted,
                policy_version=current_policy_version(),
                channel=ConsentRecord.Channel.PORTAL,
                request=request,
            )
            messages.success(
                request,
                _("Согласие обновлено.") if granted else _("Согласие отозвано."),
            )
        return redirect("clients:onboarding_consent", token=token)

    status = ConsentRecord.current_status(client)
    consent_rows = [
        {
            "purpose": choice,
            "label": label,
            "granted": ConsentRecord.is_granted(client, choice),
            "record": status.get(choice),
        }
        for choice, label in ConsentRecord.Purpose.choices
    ]
    return render(
        request,
        "clients/onboarding/consent.html",
        {
            "session": session,
            "app_settings": AppSettings.get_solo(),
            "consent_rows": consent_rows,
        },
    )


def onboarding_my_data(request: HttpRequest, token: str) -> HttpResponse:
    """Subject-facing data-rights centre: download own data or request erasure.

    Implements RODO art. 15/20 (access + portability, JSON export) and art. 17
    (right to erasure — recorded as a request that staff action out of band).
    """
    import json

    from django.contrib import messages
    from django.http import HttpResponse as DjangoHttpResponse

    from clients.services.data_export import build_subject_data

    session = onboarding_views.check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))
    auth_redirect = _auth_redirect(request, session, token)
    if auth_redirect:
        return auth_redirect

    client = session.client

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "export":
            payload = build_subject_data(client)
            response = DjangoHttpResponse(
                json.dumps(payload, ensure_ascii=False, indent=2),
                content_type="application/json",
            )
            response["Content-Disposition"] = f'attachment; filename="my-data-{client.pk}.json"'
            return response
        if action == "erasure_request":
            from clients.services.erasure import request_erasure

            was_open = client.erasure_requested_at is not None
            request_erasure(client)
            if not was_open:
                # First request for this subject → open the staff review task.
                _create_erasure_task(session)
            messages.success(
                request,
                _("Запрос на удаление данных получен. Мы свяжемся с вами."),
            )
            return redirect("clients:onboarding_my_data", token=token)
        return HttpResponseBadRequest(_("Некорректный запрос."))

    return render(
        request,
        "clients/onboarding/my_data.html",
        {
            "session": session,
            "erasure_requested_at": client.erasure_requested_at,
        },
    )


def _create_erasure_task(session: ClientOnboardingSession) -> None:
    from clients.models import StaffTask

    case = onboarding_views._session_case(session)
    StaffTask.objects.create(
        client=session.client,
        case=case,
        task_type="internal_note",
        title=str(_("Запрос на удаление данных (RODO art. 17)")),
        description=str(_("Субъект данных запросил удаление своих данных через личный кабинет.")),
        priority="high",
        is_auto_created=True,
    )
