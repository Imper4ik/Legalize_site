import logging
from datetime import timedelta
from typing import Any, cast

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
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
from django.utils import timezone
from django.utils.translation import gettext as _

from clients.constants import SELF_ONBOARDING_SLUG, DocumentType
from clients.forms import DocumentUploadForm
from clients.models import (
    Case,
    Client,
    ClientDigitalAccess,
    ClientOnboardingSession,
    Document,
    MOSApplicationData,
)
from clients.services.access import accessible_clients_queryset
from clients.services.document_workflow import upload_client_document
from clients.services.notifications import notify_staff_about_fingerprint_invitation_upload
from clients.services.onboarding_purposes import (
    ONBOARDING_PURPOSE_CHOICES,
    apply_onboarding_purpose_to_client,
    clear_onboarding_notifications_cache,
    normalize_onboarding_purpose,
    purpose_label,
)
from clients.services.onboarding_tokens import generate_onboarding_token, hash_onboarding_token
from clients.services.workflow_transitions import transition_case_workflow
from clients.use_cases.client_records import finalize_client_creation
from clients.views.base import role_required_view
from legalize_site.utils.files import build_protected_file_response
from legalize_site.utils.http import request_is_ajax

EDITABLE_MOS_STATUSES = {"draft", "client_filling", "needs_correction"}
CONTACT_SYNC_FIELDS = ("first_name", "last_name", "phone", "email")
logger = logging.getLogger(__name__)


def _mos_data_is_editable(mos_data: MOSApplicationData | None) -> bool:
    return mos_data is None or mos_data.status in EDITABLE_MOS_STATUSES


def _mos_documents_are_editable(mos_data: MOSApplicationData | None) -> bool:
    return mos_data is None or mos_data.status in {
        "draft",
        "client_filling",
        "client_completed",
        "staff_review",
        "needs_correction",
        "submitted_in_mos",
        "fingerprints",
        "waiting_decision",
    }


def _locked_response(request: HttpRequest, session: ClientOnboardingSession) -> HttpResponse:
    mos_data = _get_scoped_mos(session)
    status_display = mos_data.get_status_display() if mos_data else ""

    if (
        request_is_ajax(request)
        or request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
    ):
        return JsonResponse({"status": "locked", "message": _("This onboarding form is locked.")}, status=403)

    response = render(request, "clients/onboarding/locked.html", {
        "session": session,
        "status_display": status_display,
    })
    response.status_code = 403
    return response


def _sync_contact_fields_to_client(client: Client, **values: str) -> None:
    update_fields: list[str] = []
    for field_name in CONTACT_SYNC_FIELDS:
        value = (values.get(field_name) or "").strip()
        if value and getattr(client, field_name) != value:
            setattr(client, field_name, value)
            update_fields.append(field_name)
    if update_fields:
        client.save(update_fields=update_fields)


def _get_effective_document_purpose(client: Client, mos_data: MOSApplicationData | None = None) -> str:
    return client.get_document_requirement_purpose()


def _purpose_context(client: Client, mos_data: MOSApplicationData | None) -> dict[str, str | bool]:
    effective_purpose = _get_effective_document_purpose(client, mos_data)
    client_selected_purpose = mos_data.mos_purpose if mos_data else ""
    original_client_purpose = client.application_purpose
    return {
        "effective_purpose": effective_purpose,
        "client_selected_purpose": client_selected_purpose,
        "original_client_purpose": original_client_purpose,
        "effective_purpose_label": purpose_label(effective_purpose),
        "client_selected_purpose_label": purpose_label(client_selected_purpose),
        "original_client_purpose_label": purpose_label(client.get_document_requirement_purpose()),
        "purpose_mismatch": bool(client_selected_purpose and client_selected_purpose != client.get_document_requirement_purpose()),
    }


def _session_case(session: ClientOnboardingSession) -> Case | None:
    """The Case the current portal/onboarding request operates on.

    ``case_link`` sessions are bound to a single case; ``client_portal`` sessions
    carry the case the client picked for this Django session. The value is set by
    :func:`check_onboarding_session` after the ownership/archive re-validation, so
    it is always either ``None`` or a case that belongs to the session's client
    and is not archived (spec section 1).
    """
    return getattr(session, "active_case", None)


def _require_portal_case(
    request: HttpRequest, session: ClientOnboardingSession, token: str
) -> HttpResponse | None:
    """Redirect portal users to the case picker until they have chosen a case.

    Case-scoped steps must never run without a selected case for a
    ``client_portal`` session, otherwise the MOS/Document lookups would fall back
    to the ambiguous legacy resolution.
    """
    if session.scope == "client_portal" and _session_case(session) is None:
        return redirect("clients:onboarding_select_case", token=token)
    return None


def _ensure_mos(client: Client, case: Any = None) -> tuple[MOSApplicationData, bool]:
    """Create/fetch the MOS record for a specific case (spec section 6).

    Self-onboarding must scope MOS data to a case, not the client. When the
    caller already knows the case it is used directly; otherwise the client's
    single active case is resolved. Ambiguous multi-case clients fall back to
    the legacy client-only lookup (which the model resolves or rejects).
    """
    from clients.services.cases import resolve_single_active_case

    resolved_case = case or resolve_single_active_case(client)
    if resolved_case is not None:
        return MOSApplicationData.objects.get_or_create(client=client, case=resolved_case)
    return MOSApplicationData.objects.get_or_create(client=client)


def _get_scoped_mos(session: ClientOnboardingSession) -> MOSApplicationData | None:
    """Return the MOS record for the session's active case, or None.

    Replaces the legacy ``client.mos_application_data`` (``.first()``) accessor so
    a multi-case client only ever sees the MOS of the case in scope.
    """
    case = _session_case(session)
    if case is not None:
        return MOSApplicationData.objects.filter(client=session.client, case=case).first()
    return MOSApplicationData.objects.filter(client=session.client).first()


def _save_onboarding_purpose(mos_data: MOSApplicationData, selected_purpose: str) -> None:
    mos_data.mos_purpose = selected_purpose
    update_fields = ["mos_purpose", "updated_at"]
    if mos_data.status == "draft":
        mos_data.status = "client_filling"
        update_fields.append("status")
    mos_data.save(update_fields=update_fields)
    clear_onboarding_notifications_cache(mos_data.client)


class OnboardingLinkExpired(Exception):
    pass


def check_onboarding_session(
    token: str,
    allowed_statuses: tuple[str, ...] = ("created", "active"),
    request: HttpRequest | None = None,
) -> ClientOnboardingSession | None:
    if token == SELF_ONBOARDING_SLUG:
        if request and request.user.is_authenticated and hasattr(request.user, "client_profile"):
            client = request.user.client_profile
            session = ClientOnboardingSession.objects.filter(
                client=client,
                expires_at__gt=timezone.now()
            ).exclude(status__in=["revoked", "expired"]).first()
            if not session:
                from clients.services.onboarding_tokens import generate_onboarding_token
                _, token_hash = generate_onboarding_token()
                # Self-onboarding is a client portal: it must never carry/auto-pick
                # a Case. The case is chosen per-request and kept server-side. MOS
                # data is created lazily once a case is selected (spec section 1).
                session = ClientOnboardingSession.objects.create(
                    client=client,
                    scope="client_portal",
                    case=None,
                    token_hash=token_hash,
                    status="active",
                    expires_at=timezone.now() + timedelta(days=7),
                )
                ClientDigitalAccess.objects.get_or_create(client=client)
            elif session.status == "created" and "active" in allowed_statuses:
                session.status = "active"
                session.save(update_fields=["status"])
                ClientDigitalAccess.objects.get_or_create(client=client)
            session.token_hash = SELF_ONBOARDING_SLUG
            session.client = client
        else:
            return None
    else:
        token_h = hash_onboarding_token(token)
        session_any = ClientOnboardingSession.objects.filter(token_hash=token_h).first()
        if session_any:
            if session_any.expires_at <= timezone.now() or session_any.status in ("revoked", "expired"):
                raise OnboardingLinkExpired()

        session = ClientOnboardingSession.objects.filter(token_hash=token_h, expires_at__gt=timezone.now()).first()
        if not session or session.status not in allowed_statuses:
            return None
        if session.status == "created" and "active" in allowed_statuses:
            session.status = "active"
            session.save(update_fields=["status"])
        session.token_hash = token
        session.client = Client.objects.defer("passport_num").get(pk=session.client_id)

    # An archived client never has an accessible portal/onboarding context.
    if session.client.archived_at is not None:
        return None

    # Валидация scope и согласованности дела. The resolved case is attached to
    # the session as ``active_case`` for the view layer to consume.
    session.active_case = None  # type: ignore[attr-defined]
    case_id: Any = None
    if session.scope == "case_link":
        # case_link sessions are permanently bound to one case; without it there
        # is nothing to show.
        if not session.case_id:
            return None
        case_id = session.case_id
    elif session.scope == "client_portal":
        # Never auto-assign a Case for the portal: the client picks one and it
        # is kept server-side in the Django session. An untrusted GET/POST value
        # is only honoured after the ownership/archive checks below.
        if request:
            case_id = request.session.get("case_id")

    if case_id:
        case = Case.all_objects.filter(pk=case_id).first()
        case_is_valid = (
            case is not None
            and case.client_id == session.client_id
            and case.archived_at is None
        )
        if case_is_valid:
            session.active_case = case  # type: ignore[attr-defined]
            # Only the portal persists the chosen case in the Django session;
            # case_link derives it from the session row itself.
            if request and session.scope == "client_portal":
                request.session["case_id"] = case.id
        else:
            if session.scope == "case_link":
                # The bound case vanished/was archived: the link is dead.
                return None
            # Portal: drop the stale/forged selection and ask again (no leak).
            if request:
                request.session.pop("case_id", None)

    return session

def _should_bypass_client_auth(request: HttpRequest) -> bool:
    if not request.user.is_authenticated:
        return False
    if request.user.is_staff:
        return True
    from clients.services.roles import user_has_any_role
    return user_has_any_role(request.user, "Admin", "Manager", "Staff")

def check_client_auth(request: HttpRequest, session: ClientOnboardingSession, token: str) -> HttpResponse | None:
    if _should_bypass_client_auth(request):
        return None

    client = session.client
    if not client.user or not client.user.has_usable_password():
        return redirect("clients:onboarding_set_password", token=token)

    if not request.user.is_authenticated or request.user != client.user:
        messages.info(request, _("Пожалуйста, войдите в свой аккаунт для продолжения."))
        login_url = reverse("account_login")
        return redirect(f"{login_url}?email={client.email}")

    return None

def _validate_email_domain_dns(email: str) -> bool:
    import socket

    from django.conf import settings
    if getattr(settings, "TESTING", False):
        return True
    if "@" not in email:
        return False
    domain = email.split("@")[-1].strip()
    try:
        socket.getaddrinfo(domain, None)
        return True
    except Exception:
        return False


def _split_onboarding_full_name(full_name: str) -> tuple[str, str] | None:
    parts = full_name.split()
    if len(parts) < 2:
        return None
    return " ".join(parts[1:]), parts[0]


def _mark_user_email_verified(user: Any, email: str) -> None:
    from allauth.account.models import EmailAddress

    email_address = EmailAddress.objects.filter(user=user, email__iexact=email).first()
    if email_address is None:
        email_address = EmailAddress.objects.create(
            user=user,
            email=email,
            primary=True,
            verified=True,
        )
    else:
        email_address.email = email
        email_address.primary = True
        email_address.verified = True
        email_address.save(update_fields=["email", "primary", "verified"])

    EmailAddress.objects.filter(user=user).exclude(pk=email_address.pk).update(primary=False)


def onboarding_set_password(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))

    client = session.client

    if client.user and client.user.has_usable_password():
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
        elif not _validate_email_domain_dns(email_val):
            error_message = _("Не удалось подтвердить существование домена почты. Пожалуйста, проверьте адрес на опечатки.")
        elif password != password_confirm:
            error_message = _("Пароли не совпадают.")
        elif len(password) < 8:
            error_message = _("Пароль должен быть не менее 8 символов.")
        else:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            first_name, last_name = parsed_name
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
            except Exception as e:
                error_message = _("Произошла ошибка при сохранении аккаунта: {error}").format(error=str(e))

    return render(request, "clients/onboarding/set_password.html", {
        "session": session,
        "email": email_val,
        "phone": phone_val,
        "full_name": full_name_val,
        "error_message": error_message,
    })


def _document_source_hint(doc_type: str) -> str:
    hints = {
        DocumentType.PHOTOS.value: _("Фото 45x35 мм можно сделать в фотоателье или фотокабине. Попросите формат do karty pobytu."),
        DocumentType.PAYMENT_CONFIRMATION.value: _("Сделайте оплату банковским переводом или в кассе, затем загрузите подтверждение платежа."),
        DocumentType.STUDY_APPLICATION_FEE.value: _("Оплату можно сделать банковским переводом на счёт управления (urząd); сохраните подтверждение из банка."),
        DocumentType.WORK_PERMIT_FEE.value: _("Оплату можно сделать банковским переводом на счёт управления (urząd); сохраните подтверждение 440 zł и 17 zł за доверенность, если она нужна."),
        "family_reunification_fee": _("Оплату можно сделать банковским переводом на счёт управления (urząd); сохраните подтверждение платежа и доверенности, если она нужна."),
        DocumentType.PASSPORT.value: _("Отсканируйте или сфотографируйте действующий паспорт. Если паспорт нужно оформить заново, обратитесь в консульство или орган вашей страны."),
        DocumentType.RESIDENCE_CARD.value: _("Отсканируйте или сфотографируйте текущую карту побыту с двух сторон, если она у вас есть."),
        DocumentType.ENROLLMENT_CERTIFICATE.value: _("Закажите справку в деканате, student office или личном кабинете вашей учёбы."),
        DocumentType.TUITION_FEE_STATEMENT.value: _("Запросите справку о стоимости обучения в деканате, student office или бухгалтерии учебного заведения."),
        DocumentType.TUITION_FEE_PROOF.value: _("Возьмите подтверждение оплаты обучения в банковском приложении или в бухгалтерии учебного заведения."),
        DocumentType.GRADES.value: _("Оценки или свидетельства можно получить в деканате, student office, школе или в электронном кабинете ученика/студента."),
        DocumentType.HEALTH_INSURANCE.value: _("Полис можно получить у страховщика, работодателя, в ZUS/eZUS или NFZ. Подойдёт документ с подтверждением активной страховки."),
        DocumentType.ADDRESS_PROOF.value: _("Обычно это договор аренды от владельца жилья, подтверждение meldunek из управления (urząd) или документы об оплате проживания."),
        DocumentType.FINANCIAL_PROOF.value: _("Подготовьте выписку из банка, справку о доходах, документы спонсора или другое подтверждение средств на проживание."),
        DocumentType.ZALACZNIK_NR_1.value: _("Załącznik nr 1 заполняет и подписывает работодатель. Обратитесь в отдел кадров, HR или бухгалтерию."),
        DocumentType.EMPLOYMENT_CONTRACT.value: _("Копию договора о работе или zlecenie можно получить у работодателя, в HR или бухгалтерии."),
        DocumentType.WORK_PERMISSION.value: _("Oświadczenie или zezwolenie na pracę выдаёт работодатель. Если у вас польский диплом, загрузите диплом и suplement."),
        DocumentType.PIT_PROOF.value: _("PIT-37 с подтверждением подачи можно скачать в e-Urząd Skarbowy на podatki.gov.pl или получить у бухгалтера."),
        DocumentType.TAX_CLEARANCE_EMPLOYER.value: _("Этот документ работодатель получает в ZUS/eZUS. Попросите HR или бухгалтерию подготовить справку."),
        DocumentType.TAX_CLEARANCE_FOREIGNER.value: _("Справку о взносах можно получить в ZUS/eZUS или запросить у работодателя/бухгалтерии."),
        DocumentType.NO_DEPENDENTS_STATEMENT.value: _("Справку об отсутствии налоговой задолженности можно получить в e-Urząd Skarbowy или в налоговом ужонде."),
        DocumentType.ZUS_RCA_OR_INSURANCE.value: _("ZUS RCA можно скачать в ZUS PUE/eZUS в разделе Ubezpieczony -> Raporty или запросить у бухгалтера работодателя."),
        DocumentType.ZUS_CONTRIBUTION_HISTORY.value: _("Справку о przebiegu ubezpieczenia можно заказать в ZUS/eZUS или в отделении ZUS."),
        DocumentType.EMPLOYER_TAX_RETURN.value: _("CIT/PIT работодателя подготовит бухгалтерия работодателя."),
        DocumentType.ZUS_EMPLOYEE_COUNT.value: _("Справку о количестве сотрудников и взносах работодатель получает в ZUS/eZUS. Обратитесь в HR или бухгалтерию."),
        DocumentType.STATEMENT_X.value: _("Шаблон заявления выдаёт менеджер или юрист. Заполните и подпишите его после проверки данных."),
        DocumentType.MAINTENANCE_STATEMENT.value: _("Заявление об обеспечении заполняет и подписывает человек, который будет вас содержать. Шаблон можно получить у менеджера."),
        DocumentType.WEZWANIE.value: _("Загрузите письмо/wezwanie из управления (urząd), которое пришло по почте, ePUAP или MOS: дата отпечатков, требования или номер дела."),
        DocumentType.FINGERPRINT_CONFIRMATION.value: _("Подтверждение выдаёт ужонд после сдачи отпечатков пальцев."),
        "sponsor_residence_decision_or_card": _("Спонсор должен отсканировать свою карту побыту, решение о побыте или другой документ, подтверждающий легальное пребывание."),
        "sponsor_income_proof": _("Документы о доходе спонсора можно получить у работодателя, в бухгалтерии, банке, ZUS или налоговом ужонде."),
        "marriage_certificate": _("Свидетельство о браке получите в ЗАГСе/USC страны регистрации брака; для Польши обычно нужен присяжный перевод."),
        "joint_family_life_evidence": _("Подойдут договор аренды, счета, совместные документы, фото или другие доказательства совместной семейной жизни."),
        "outside_poland_consent": _("Согласие можно оформить у нотариуса или в консульстве; при необходимости добавьте присяжный перевод."),
        "birth_certificate": _("Свидетельство о рождении получите в ЗАГСе/USC страны рождения; для Польши обычно нужен присяжный перевод."),
        "parental_authority_docs": _("Документы об опеке или родительских правах можно получить в суде, ЗАГСе/USC или у нотариуса; при необходимости добавьте перевод."),
        "second_parent_consent": _("Согласие второго родителя оформляется у нотариуса или в консульстве. Решение суда также подойдёт, если оно заменяет согласие."),
        "school_certificate": _("Справку из школы можно получить в секретариате школы или электронном кабинете."),
        "outside_poland_child_consent": _("Согласие законного представителя можно оформить у нотариуса или в консульстве; при необходимости добавьте перевод."),
    }
    return hints.get(doc_type, _("Если не знаете, где получить этот документ, напишите менеджеру, и мы подскажем точное место."))


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

    auth_redirect = check_client_auth(request, session, token)
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
    auth_redirect = check_client_auth(request, session, token)
    if auth_redirect:
        return auth_redirect
    case_redirect = _require_portal_case(request, session, token)
    if case_redirect:
        return case_redirect

    client = session.client
    mos_data, _created = _ensure_mos(client, _session_case(session))

    if not _mos_data_is_editable(mos_data):
        return _locked_response(request, session)

    current_purpose = mos_data.mos_purpose or client.get_document_requirement_purpose()

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
        "original_client_purpose": client.application_purpose,
        "original_client_purpose_label": purpose_label(client.get_document_requirement_purpose()),
    })


def onboarding_document_upload(request: HttpRequest, token: str, doc_type: str) -> HttpResponse:
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Invalid or expired onboarding link."))
    auth_redirect = check_client_auth(request, session, token)
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
    auth_redirect = check_client_auth(request, session, token)
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
    auth_redirect = check_client_auth(request, session, token)
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
    auth_redirect = check_client_auth(request, session, token)
    if auth_redirect:
        return auth_redirect
    case_redirect = _require_portal_case(request, session, token)
    if case_redirect:
        return case_redirect

    mos_data = get_object_or_404(
        MOSApplicationData, client=session.client, case=_session_case(session)
    )

    return render(request, "clients/onboarding/review.html", {"session": session, "mos_data": mos_data})

@role_required_view("Admin", "Manager", "Staff")
def generate_onboarding_link(request: HttpRequest, client_id: int) -> HttpResponse:
    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), id=client_id)
    selected_purpose = (request.POST.get("application_purpose", "").strip() or None) if request.method == "POST" else None
    if selected_purpose:
        try:
            selected_purpose = normalize_onboarding_purpose(selected_purpose)
        except ValueError:
            if request_is_ajax(request):
                return JsonResponse({"status": "error", "message": _("Invalid application purpose")}, status=400)
            return HttpResponseBadRequest(_("Invalid application purpose."))

    intake_type = request.POST.get("intake_type", "").strip() if request.method == "POST" else ""
    if not intake_type:
        # Default guess reads progress from the client's single active case (§4).
        from clients.services.cases import resolve_single_active_case

        active_case = resolve_single_active_case(client)
        has_progress = bool(active_case and (active_case.submission_date or active_case.fingerprints_date))
        intake_type = "join" if has_progress else "new"

    token, token_hash = generate_onboarding_token()
    payment = client.payments.filter(status__in=["paid", "partial"]).first()

    with transaction.atomic():
        mos_data, _created = _ensure_mos(client)
        ClientDigitalAccess.objects.get_or_create(client=client)
        if selected_purpose:
            changed_fields = apply_onboarding_purpose_to_client(client, selected_purpose)
            if mos_data.mos_purpose:
                mos_data.mos_purpose = ""
                mos_data.save(update_fields=["mos_purpose", "updated_at"])
            clear_onboarding_notifications_cache(client)
            if changed_fields:
                from clients.services.activity import log_client_activity
                log_client_activity(
                    client=client,
                    actor=request.user,
                    event_type="onboarding_link_purpose_set",
                    summary="Onboarding link purpose set by staff",
                    metadata={"selected_purpose": selected_purpose, "changed_fields": changed_fields},
                )

        if intake_type == "join":
            mos_data.new_residence_card_application_status = "yes"
            mos_data.new_residence_card_updated_at = timezone.now()

            # Smart transition logic based on the case's existing dates (§4).
            case = mos_data.case
            if case is None:
                messages.error(request, _("Не удалось определить дело для заявки."))
                return redirect("clients:client_detail", pk=client.pk)
            target_stage = "waiting_decision" if case.fingerprints_date else "fingerprints"
            try:
                with transaction.atomic():
                    if case.workflow_stage != target_stage:
                        transition_case_workflow(case=case, target_stage=target_stage, actor=request.user, save=True)
                    mos_data.status = target_stage
                    mos_data.save(update_fields=["new_residence_card_application_status", "new_residence_card_updated_at", "status", "updated_at"])
            except ValidationError as exc:
                messages.error(request, str(exc))
                return redirect("clients:client_detail", pk=client.pk)
            except Exception:
                logger.exception("Unexpected error while preparing join onboarding", extra={"client_id": client.pk})
                messages.error(request, _("Unexpected error while updating application status."))
                return redirect("clients:client_detail", pk=client.pk)
        elif intake_type == "new":
            mos_data.new_residence_card_application_status = "no"
            mos_data.save(update_fields=["new_residence_card_application_status", "updated_at"])

        # Staff-generated links are case-scoped (case_link): they point at the
        # specific case the MOS data was resolved for (spec section 1).
        ClientOnboardingSession.objects.create(
            client=client,
            payment=payment,
            scope="case_link",
            case=mos_data.case,
            token_hash=token_hash,
            status="created",
            expires_at=timezone.now() + timedelta(days=7),
        )

    if request_is_ajax(request):
        link = request.build_absolute_uri(
            reverse("clients:onboarding_start", kwargs={"token": token})
        )
        return JsonResponse({
            "status": "ok",
            "link": link,
            "message": _("Ссылка на онбординг скопирована!")
        })

    messages.success(request, _("Ссылка на онбординг успешно создана."))
    return redirect("clients:client_detail", pk=client.id)

def onboarding_personal_data(request: HttpRequest, token: str) -> HttpResponse:
    return redirect("clients:onboarding_passport", token=token)


@role_required_view("Admin", "Manager", "Staff")
def quick_create_client_onboarding(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": _("Method not allowed")}, status=405)

    first_name = request.POST.get("first_name", "").strip() or "Новый"
    last_name = request.POST.get("last_name", "").strip() or "Клиент"
    email = request.POST.get("email", "").strip()
    phone = request.POST.get("phone", "").strip()
    language = request.POST.get("language", "pl").strip()
    try:
        selected_purpose = normalize_onboarding_purpose(request.POST.get("application_purpose", "study") or "study")
    except ValueError:
        return JsonResponse({"status": "error", "message": _("Invalid application purpose")}, status=400)
    application_purpose = "family" if selected_purpose in {"family_spouse", "family_child"} else selected_purpose
    family_role = selected_purpose if application_purpose == "family" else ""

    intake_type = request.POST.get("intake_type", "new").strip()

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
                family_role=family_role,
                status="new",
                workflow_stage="new_client",
            )
            finalize_client_creation(
                client=client,
                actor=request.user,
            )

            mos_data, _created = _ensure_mos(client)
            if intake_type == "join":
                mos_data.new_residence_card_application_status = "yes"
                mos_data.new_residence_card_updated_at = timezone.now()
                target_stage = "fingerprints"
                case = mos_data.case
                if case is None:
                    messages.error(request, _("Не удалось определить дело для заявки."))
                    return redirect("clients:client_add")
                try:
                    with transaction.atomic():
                        transition_case_workflow(case=case, target_stage=target_stage, actor=request.user, save=True)
                        mos_data.status = target_stage
                        mos_data.save(update_fields=["new_residence_card_application_status", "new_residence_card_updated_at", "status", "updated_at"])
                except ValidationError as exc:
                    messages.error(request, str(exc))
                    return redirect("clients:client_add")
                except Exception:
                    logger.exception("Unexpected error while quick-creating join onboarding", extra={"client_id": client.pk})
                    messages.error(request, _("Unexpected error while updating application status."))
                    return redirect("clients:client_add")
            elif intake_type == "new":
                mos_data.new_residence_card_application_status = "no"
                mos_data.save(update_fields=["new_residence_card_application_status", "updated_at"])

            token, token_hash = generate_onboarding_token()
            # A freshly created client has exactly one case: the staff link is
            # case-scoped to it (spec section 1).
            ClientOnboardingSession.objects.create(
                client=client,
                scope="case_link",
                case=mos_data.case,
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
            "message": _("Клиент добавлен и ссылка скопирована!")
        })
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


def onboarding_auto_save(request: HttpRequest, token: str) -> HttpResponse:
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": _("Method not allowed")}, status=405)

    session = check_onboarding_session(token, request=request)
    if not session:
        return JsonResponse({"status": "error", "message": _("Invalid token")}, status=403)
    auth_redirect = check_client_auth(request, session, token)
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

    auth_redirect = check_client_auth(request, session, token)
    if auth_redirect:
        return auth_redirect

    question_text = request.POST.get("question", "").strip()
    if not question_text:
        return HttpResponseBadRequest(_("Текст вопроса не может быть пустым."))

    client = session.client

    from django.urls import reverse

    from clients.models import StaffTask

    task = StaffTask.objects.create(
        client=client,
        title=f"Вопрос от клиента: {client.get_full_name()}",
        description=f"Клиент задал вопрос через приложение:\n\n{question_text}",
        priority="high",
        status="open",
        assignee=None,
        created_by=client.user,
    )

    from clients.services.activity import log_client_activity
    log_client_activity(
        client=client,
        actor=client.user,
        event_type="comment",
        summary=f"Задан вопрос сотруднику: '{question_text[:50]}...'",
        details=question_text,
        task=task,
    )

    messages.success(request, _("Ваш вопрос успешно отправлен. Сотрудник свяжется с вами!"))

    next_url = request.POST.get("next") or reverse("clients:onboarding_start", kwargs={"token": token})
    return redirect(next_url)
