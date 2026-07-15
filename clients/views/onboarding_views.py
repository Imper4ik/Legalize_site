import logging
from typing import Any, cast

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseNotAllowed,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _

from clients.constants import SELF_ONBOARDING_SLUG, DocumentType
from clients.forms import DocumentUploadForm
from clients.models import (
    Case,
    Client,
    ClientDigitalAccess,
    Document,
    MOSApplicationData,
)
from clients.services.document_workflow import upload_client_document
from clients.services.notifications import notify_staff_about_fingerprint_invitation_upload
from clients.services.onboarding_purposes import (
    ONBOARDING_PURPOSE_CHOICES,
    clear_onboarding_notifications_cache,
    normalize_onboarding_purpose,
    purpose_label,
)

# --- split modules ------------------------------------------------------------
# Session/auth helpers and staff entry points were extracted; re-export them so
# sibling views (onboarding_step_return accesses them as module attributes),
# clients.views.__init__ and the URLconf keep working unchanged.
from clients.views.onboarding_access import (  # noqa: F401
    EDITABLE_MOS_STATUSES,
    ONBOARDING_LINK_TTL,
    OnboardingLinkExpired,
    _document_source_hint,
    _ensure_mos,
    _get_effective_document_purpose,
    _get_scoped_mos,
    _locked_response,
    _mark_user_email_verified,
    _mos_data_is_editable,
    _mos_documents_are_editable,
    _purpose_context,
    _require_portal_case,
    _save_onboarding_purpose,
    _session_case,
    _should_bypass_client_auth,
    _split_onboarding_full_name,
    _sync_contact_fields_to_client,
    _validate_portal_email,
    check_client_auth,
    check_client_auth_token_link,
    check_onboarding_session,
)
from clients.views.onboarding_staff_views import (  # noqa: F401
    generate_onboarding_link,
    quick_create_client_onboarding,
)
from legalize_site.utils.files import build_protected_file_response

logger = logging.getLogger(__name__)





def onboarding_set_password(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))

    client = session.client

    raw_token_can_reset_password = token != SELF_ONBOARDING_SLUG
    if client.user and client.user.has_usable_password() and not raw_token_can_reset_password:
        if request.user.is_authenticated and request.user == client.user:
            return redirect("clients:onboarding_start", token=token)
        messages.info(request, _("У вас уже есть аккаунт. Пожалуйста, войдите в систему."))
        login_url = reverse("account_login")
        return redirect(f"{login_url}?email={client.email}")

    error_message = None
    full_name_val = " ".join(part for part in [client.last_name, client.first_name] if part).strip()
    email_val = client.email or ""
    phone_val = client.phone or ""

    if request.method == "POST":
        full_name_val = " ".join(request.POST.get("full_name", "").split())
        email_val = request.POST.get("email", "").strip().lower()
        phone_val = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "")
        password_confirm = request.POST.get("password_confirm", "")
        parsed_name = _split_onboarding_full_name(full_name_val)

        if not full_name_val:
            error_message = _("Пожалуйста, укажите ФИО.")
        elif parsed_name is None:
            error_message = _("Введите ФИО полностью: фамилия и имя.")
        elif not email_val:
            error_message = _("Пожалуйста, укажите адрес электронной почты.")
        else:
            error_message = _validate_portal_email(email_val, client)

        if not error_message and password != password_confirm:
            error_message = _("Пароли не совпадают.")
        elif not error_message and len(password) < 8:
            error_message = _("Пароль должен быть не менее 8 символов.")
        elif not error_message:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            # parsed_name is guaranteed non-None here: the branch above sets
            # error_message when it is None, and this elif requires no error.
            first_name, last_name = cast("tuple[str, str]", parsed_name)
            existing_user = User.objects.filter(email__iexact=email_val).first()
            user = None

            try:
                with transaction.atomic():
                    if existing_user:
                        linked_client = Client.all_objects.filter(user=existing_user).first()
                        if linked_client:
                            if linked_client.pk == client.pk:
                                user = existing_user
                            elif linked_client.archived_at is not None:
                                Client.all_objects.filter(pk=linked_client.pk).update(user=None)
                                user = existing_user
                            else:
                                error_message = _("Этот адрес электронной почты уже используется в системе другим активным клиентом.")
                        else:
                            user = existing_user

                        if not error_message and user:
                            user.email = email_val
                            user.first_name = first_name
                            user.last_name = last_name
                            user.set_password(password)
                            user.is_active = True
                            user.save()
                    else:
                        user = User.objects.create_user(
                            email=email_val,
                            password=password,
                            first_name=first_name,
                            last_name=last_name,
                        )

                    if not error_message and user:
                        client.email = email_val
                        client.first_name = first_name
                        client.last_name = last_name
                        client.phone = phone_val
                        client.user = user
                        client.save(update_fields=["email", "first_name", "last_name", "phone", "user"])
                        _mark_user_email_verified(user, email_val)

                        from django.contrib.auth import login
                        login(request, user, backend="django.contrib.auth.backends.ModelBackend")

                        messages.success(request, _("Аккаунт успешно создан. Вы вошли в личный кабинет клиента."))
                        return redirect("clients:onboarding_start", token=token)
            except IntegrityError:
                # Never leak raw database/schema details to the public portal.
                logger.exception("Onboarding set-password hit an integrity error", extra={"client_id": client.pk})
                error_message = _("Такой аккаунт уже существует. Попробуйте войти или обратитесь к сотруднику.")
            except Exception:
                logger.exception("Onboarding set-password failed", extra={"client_id": client.pk})
                error_message = _("Не удалось сохранить аккаунт. Попробуйте ещё раз или обратитесь к сотруднику.")

    return render(request, "clients/onboarding/set_password.html", {
        "session": session,
        "email": email_val,
        "phone": phone_val,
        "full_name": full_name_val,
        "error_message": error_message,
    })


def onboarding_select_case(request: HttpRequest, token: str) -> HttpResponse:
    """Let a client_portal user pick which of their cases to work on.

    The chosen case is validated against the session's client and stored
    server-side in the Django session. A forged/foreign case id simply does not
    match the active-cases queryset and is rejected without revealing anything
    about other clients' cases (spec section 6).
    """
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))

    # case_link sessions are bound to a single case and never choose one.
    if session.scope != "client_portal":
        return redirect("clients:onboarding_start", token=token)

    auth_redirect = check_client_auth_token_link(request, session, token)
    if auth_redirect:
        return auth_redirect

    client = session.client
    active_cases = Case.objects.filter(client=client, archived_at__isnull=True).order_by("-opened_at", "-id")

    if request.method == "POST":
        chosen_case = active_cases.filter(pk=request.POST.get("case_id")).first()
        if chosen_case is None:
            messages.error(request, _("Выберите дело из списка."))
        else:
            request.session["case_id"] = chosen_case.id
            return redirect("clients:onboarding_start", token=token)

    return render(
        request,
        "clients/onboarding/select_case.html",
        {"session": session, "token": token, "active_cases": active_cases},
    )


def onboarding_purpose(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Invalid or expired onboarding link."))
    auth_redirect = check_client_auth_token_link(request, session, token)
    if auth_redirect:
        return auth_redirect
    case_redirect = _require_portal_case(request, session, token)
    if case_redirect:
        return case_redirect

    client = session.client
    case = _session_case(session)
    mos_data, _created = _ensure_mos(client, case)

    if not _mos_data_is_editable(mos_data):
        return _locked_response(request, session)

    effective_purpose = _get_effective_document_purpose(client, mos_data, case)
    current_purpose = mos_data.mos_purpose or effective_purpose

    if request.method == "POST":
        try:
            selected_purpose = normalize_onboarding_purpose(request.POST.get("mos_purpose"))
        except ValueError:
            return HttpResponseBadRequest(_("Invalid application purpose."))
        _save_onboarding_purpose(mos_data, selected_purpose)
        return redirect("clients:onboarding_start", token=token)

    return render(request, "clients/onboarding/purpose.html", {
        "session": session,
        "mos_data": mos_data,
        "purpose_choices": ONBOARDING_PURPOSE_CHOICES,
        "current_purpose": current_purpose,
        "original_client_purpose": getattr(case, "application_purpose", client.application_purpose),
        "original_client_purpose_label": purpose_label(effective_purpose),
    })


def onboarding_document_upload(request: HttpRequest, token: str, doc_type: str) -> HttpResponse:
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Invalid or expired onboarding link."))
    auth_redirect = check_client_auth_token_link(request, session, token)
    if auth_redirect:
        return auth_redirect
    case_redirect = _require_portal_case(request, session, token)
    if case_redirect:
        return case_redirect

    mos_data = _get_scoped_mos(session)
    if not _mos_documents_are_editable(mos_data):
        return _locked_response(request, session)

    if request.method == "POST":
        if not request.FILES.get("file"):
            messages.error(request, _("Выберите файл для загрузки."))
        else:
            form = DocumentUploadForm(request.POST, request.FILES, doc_type=doc_type, client=session.client)
            if form.is_valid():
                is_fingerprint_invitation = doc_type == DocumentType.WEZWANIE.value
                result = upload_client_document(
                    client=session.client,
                    doc_type=doc_type,
                    uploaded_document=form.save(commit=False),
                    actor=request.user if request.user.is_authenticated else None,
                    case=_session_case(session),
                    # Client-side wezwanie uploads use the manual scenario: do not queue OCR here,
                    # because staff must open the original file and enter fingerprints details.
                    # For passport uploads, we trigger OCR to extract details.
                    parse_requested=(doc_type == "passport"),
                )
                if is_fingerprint_invitation:
                    notify_staff_about_fingerprint_invitation_upload(
                        client=session.client,
                        document=result.document,
                        actor=request.user if request.user.is_authenticated else None,
                    )
                    messages.success(request, _("Файл загружен. Сотрудник получил уведомление."))
                else:
                    messages.success(request, _("Файл загружен. Мы сохранили его в вашем кабинете."))
            else:
                error_text = " ".join(str(error) for errors in form.errors.values() for error in errors)
                messages.error(request, _("Не удалось загрузить файл: %(errors)s") % {"errors": error_text})
    from django.utils.text import slugify
    return redirect(reverse("clients:onboarding_start", kwargs={"token": token}) + f"#doc-{slugify(doc_type)}")


def onboarding_document_preview(request: HttpRequest, token: str, doc_id: int) -> HttpResponse:
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Invalid or expired onboarding link."))
    auth_redirect = check_client_auth_token_link(request, session, token)
    if auth_redirect:
        return auth_redirect
    case_redirect = _require_portal_case(request, session, token)
    if case_redirect:
        return case_redirect

    document = get_object_or_404(
        Document, id=doc_id, client=session.client, case=_session_case(session)
    )
    return cast(HttpResponse, build_protected_file_response(document.file, as_attachment=False))


def onboarding_document_delete(request: HttpRequest, token: str, doc_id: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))
    auth_redirect = check_client_auth_token_link(request, session, token)
    if auth_redirect:
        return auth_redirect
    case_redirect = _require_portal_case(request, session, token)
    if case_redirect:
        return case_redirect

    client = session.client
    mos_data = _get_scoped_mos(session)

    if not _mos_documents_are_editable(mos_data):
        return _locked_response(request, session)

    doc = get_object_or_404(Document, id=doc_id, client=client, case=_session_case(session))
    if not doc.verified:
        from clients.use_cases.documents import delete_client_document
        delete_client_document(
            document=doc,
            actor=request.user if request.user.is_authenticated else None
        )

    from django.utils.text import slugify
    return redirect(reverse("clients:onboarding_start", kwargs={"token": token}) + f"#doc-{slugify(doc.document_type)}")


def onboarding_review(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token, allowed_statuses=("created", "active", "completed"), request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))
    auth_redirect = check_client_auth_token_link(request, session, token)
    if auth_redirect:
        return auth_redirect
    case_redirect = _require_portal_case(request, session, token)
    if case_redirect:
        return case_redirect

    mos_data = get_object_or_404(
        MOSApplicationData, client=session.client, case=_session_case(session)
    )

    return render(request, "clients/onboarding/review.html", {"session": session, "mos_data": mos_data})


def onboarding_personal_data(request: HttpRequest, token: str) -> HttpResponse:
    return redirect("clients:onboarding_passport", token=token)


def onboarding_auto_save(request: HttpRequest, token: str) -> HttpResponse:
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": _("Method not allowed")}, status=405)

    session = check_onboarding_session(token, request=request)
    if not session:
        return JsonResponse({"status": "error", "message": _("Invalid token")}, status=403)
    auth_redirect = check_client_auth_token_link(request, session, token)
    if auth_redirect:
        return JsonResponse({"status": "error", "message": _("Authentication required")}, status=401)

    if session.scope == "client_portal" and _session_case(session) is None:
        return JsonResponse({"status": "error", "message": _("Select a case first")}, status=409)

    client = session.client
    mos_data, created_mos = _ensure_mos(client, _session_case(session))
    if not _mos_data_is_editable(mos_data):
        return JsonResponse({"status": "locked", "message": _("This onboarding form is locked.")}, status=423)

    # Process digital access fields if any
    digital_access_updated = False
    if any(k in request.POST for k in ["has_pesel", "has_trusted_profile", "has_mos_account"]):
        digital_access, created_access = ClientDigitalAccess.objects.defer("pesel").get_or_create(client=client)
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

    personal_data = cast("dict[str, Any]", mos_data.personal_data) or {}
    passport_data = cast("dict[str, Any]", mos_data.passport_data) or {}

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
        mos_data.personal_data = personal_data  # type: ignore[assignment]
    if passport_dirty:
        mos_data.passport_data = passport_data  # type: ignore[assignment]

    # Process address fields
    address_dirty = False
    address_data = cast("dict[str, Any]", mos_data.address_data) or {}
    for field in ["street", "city", "postal_code", "home_country", "home_city", "home_street", "voivodeship", "powiat", "gmina", "house_number", "apartment_number"]:
        if field in request.POST:
            address_data[field] = request.POST.get(field, "")
            address_dirty = True
    if "meldunek" in request.POST:
        address_data["meldunek"] = request.POST.get("meldunek") == "yes"
        address_dirty = True
    if address_dirty:
        mos_data.address_data = address_data  # type: ignore[assignment]

    # Process travel fields
    purpose_updated = False
    if "mos_purpose" in request.POST:
        try:
            selected_purpose = normalize_onboarding_purpose(request.POST.get("mos_purpose"))
        except ValueError:
            return JsonResponse({"status": "error", "message": _("Invalid application purpose")}, status=400)
        if mos_data.mos_purpose != selected_purpose:
            mos_data.mos_purpose = selected_purpose
            purpose_updated = True
    if "legal_stay_until" in request.POST:
        val = request.POST.get("legal_stay_until", "").strip()
        if val:
            mos_data.legal_stay_until = val

    stay_data = cast("dict[str, Any]", mos_data.stay_data) or {}
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
        mos_data.stay_data = stay_data  # type: ignore[assignment]

    if "employer_email" in request.POST:
        personal_data["employer_email"] = request.POST.get("employer_email", "").strip()
        mos_data.personal_data = personal_data  # type: ignore[assignment]
    if "employer_name" in request.POST or "employer_nip" in request.POST:
        personal_data["employer_name"] = request.POST.get("employer_name", "").strip()
        personal_data["employer_nip"] = request.POST.get("employer_nip", "").strip()
        mos_data.personal_data = personal_data  # type: ignore[assignment]
    if "university_email" in request.POST:
        personal_data["university_email"] = request.POST.get("university_email", "").strip()
        mos_data.personal_data = personal_data  # type: ignore[assignment]
    if "previous_stays" in request.POST:
        mos_data.previous_stays = [request.POST.get("previous_stays", "").strip()]  # type: ignore[assignment]

    if "travel_history" in request.POST:
        mos_data.travel_history = [request.POST.get("travel_history", "")]  # type: ignore[assignment]

    # Process declarations fields
    declarations_dirty = False
    declarations = cast("dict[str, Any]", mos_data.legal_declarations) or {}
    if "criminal_record" in request.POST:
        declarations["criminal_record"] = request.POST.get("criminal_record") == "yes"
        declarations_dirty = True
    if "tax_arrears" in request.POST:
        declarations["tax_arrears"] = request.POST.get("tax_arrears") == "yes"
        declarations_dirty = True
    if declarations_dirty:
        mos_data.legal_declarations = declarations  # type: ignore[assignment]

    # Set status to client_filling if not already filled or completed
    if mos_data.status not in ["client_completed", "staff_review", "approved_by_staff", "mos_package_ready", "submitted_in_mos", "fingerprints", "waiting_decision", "decision_received", "closed"]:
        mos_data.status = "client_filling"

    mos_data.save()
    if purpose_updated:
        clear_onboarding_notifications_cache(client)
    if client_dirty:
        client.save()

    return JsonResponse({"status": "ok", "message": _("Draft auto-saved")})


def onboarding_ask_question(request: HttpRequest, token: str) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))

    auth_redirect = check_client_auth_token_link(request, session, token)
    if auth_redirect:
        return auth_redirect

    question_text = request.POST.get("question", "").strip()
    if not question_text:
        return HttpResponseBadRequest(_("Текст вопроса не может быть пустым."))

    client = session.client
    case = _session_case(session)

    from django.urls import reverse

    from clients.models import StaffTask

    task = StaffTask.objects.create(
        client=client,
        case=case,
        title=f"Вопрос от клиента: {client.get_full_name()}",
        description=f"Клиент задал вопрос через приложение:\n\n{question_text}",
        priority="high",
        status=StaffTask.STATUS_OPEN,
        assignee=None,
        created_by=client.user,
    )

    from clients.services.activity import log_client_activity
    log_client_activity(
        client=client,
        case=case,
        actor=client.user,
        event_type="comment",
        summary="Клиент задал вопрос сотруднику",
        details="",
        task=task,
    )

    messages.success(request, _("Ваш вопрос успешно отправлен. Сотрудник свяжется с вами!"))

    # Validate the client-supplied "next" so this POST endpoint cannot be used
    # as an open redirect off-site.
    next_url = (request.POST.get("next") or "").strip()
    if next_url and not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = ""
    return redirect(next_url or reverse("clients:onboarding_start", kwargs={"token": token}))
