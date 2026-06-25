import logging
from datetime import timedelta
from typing import cast

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
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from clients.constants import SELF_ONBOARDING_SLUG, DocumentType
from clients.forms import DocumentUploadForm
from clients.models import (
    Case,
    Client,
    ClientDigitalAccess,
    ClientOnboardingSession,
    Document,
    DocumentRequirement,
    MOSApplicationData,
)
from clients.services.access import accessible_clients_queryset
from clients.services.document_workflow import upload_client_document
from clients.services.intake_extraction import pre_fill_mos_data_from_ocr
from clients.services.notifications import notify_staff_about_fingerprint_invitation_upload
from clients.services.onboarding_purposes import (
    FAMILY_ONBOARDING_PURPOSES,
    ONBOARDING_PURPOSE_CHOICES,
    apply_onboarding_purpose_to_client,
    clear_onboarding_notifications_cache,
    normalize_onboarding_purpose,
    purpose_label,
)
from clients.services.onboarding_tokens import generate_onboarding_token, hash_onboarding_token
from clients.services.workflow_transitions import transition_case_workflow, transition_client_workflow
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
    client = session.client
    mos_data = getattr(client, "mos_application_data", None)
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
                session = ClientOnboardingSession.objects.create(
                    client=client,
                    token_hash=token_hash,
                    status="active",
                    expires_at=timezone.now() + timedelta(days=7),
                )
                MOSApplicationData.objects.get_or_create(client=client)
                ClientDigitalAccess.objects.get_or_create(client=client)
            elif session.status == "created" and "active" in allowed_statuses:
                session.status = "active"
                session.save(update_fields=["status"])
                MOSApplicationData.objects.get_or_create(client=client)
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
        session.client = Client.objects.defer("case_number", "passport_num").get(pk=session.client_id)

    # Валидация scope и согласованности дела
    case_id = None
    if session.scope == "case_link":
        if not session.case_id:
            return None
        case_id = session.case_id
    elif session.scope == "client_portal":
        if session.case_id is not None:
            return None
        if request:
            case_id = request.session.get("case_id")

    if case_id:
        try:
            case = Case.all_objects.get(pk=case_id)
            if case.client_id != session.client_id:
                return None
            if case.archived_at is not None:
                return None
            if session.client.archived_at is not None:
                return None
            if request:
                request.session["case_id"] = case.id
            session.case = case
        except Case.DoesNotExist:
            return None
    elif session.scope == "case_link":
        return None

    return session

def check_portal_case_selected(request: HttpRequest, session: ClientOnboardingSession, token: str) -> HttpResponse | None:
    if session.scope == "client_portal" and not request.session.get("case_id"):
        return redirect("clients:onboarding_select_case", token=token)
    return None

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


def _mark_user_email_verified(user, email: str) -> None:
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


def onboarding_start(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))
    auth_redirect = check_client_auth(request, session, token)
    if auth_redirect:
        return auth_redirect
    case_redirect = check_portal_case_selected(request, session, token)
    if case_redirect:
        return case_redirect

    client = session.client
    mos_data = MOSApplicationData.objects.filter(client=client, case=session.case).first()

    if request.method == "POST":
        if not _mos_data_is_editable(mos_data):
            return _locked_response(request, session)
        return redirect("clients:onboarding_digital_access", token=token)

    purpose_ctx = _purpose_context(client, mos_data)
    effective_purpose = str(purpose_ctx["effective_purpose"])
    language = translation.get_language() or client.language
    required_docs_catalog = DocumentRequirement.catalog_for(purpose=effective_purpose, language=language)
    fingerprint_invitation_doc_type = DocumentType.WEZWANIE.value

    existing_documents = list(Document.objects.filter(case=session.case).order_by("document_type", "-uploaded_at"))
    existing_map = {document.document_type: document.id for document in existing_documents}

    from datetime import date
    today = date.today()
    checklist = []
    checklist_codes = set()
    for item in required_docs_catalog:
        doc_type = item["code"]
        checklist_codes.add(doc_type)
        is_uploaded = doc_type in existing_map
        doc_obj = next((d for d in existing_documents if d.document_type == doc_type), None)

        is_expired = False
        is_rejected = False
        is_verified = False
        is_awaiting_verification = False
        if doc_obj:
            is_expired = bool(doc_obj.expiry_date and doc_obj.expiry_date < today)
            is_rejected = bool(doc_obj.rejection_reason and not doc_obj.verified)
            is_verified = bool(doc_obj.verified)
            is_awaiting_verification = bool(not doc_obj.verified and not doc_obj.rejection_reason)

        checklist.append({
            "code": doc_type,
            "label": item["label"],
            "is_required": item["is_required"],
            "is_uploaded": is_uploaded,
            "doc_id": doc_obj.id if doc_obj else None,
            "verified": doc_obj.verified if doc_obj else False,
            "rejection_reason": doc_obj.rejection_reason if doc_obj else "",
            "is_expired": is_expired,
            "is_rejected": is_rejected,
            "is_verified": is_verified,
            "is_awaiting_verification": is_awaiting_verification,
            "source_hint": _document_source_hint(doc_type),
        })

    fingerprint_invitation_document = next(
        (document for document in existing_documents if document.document_type == fingerprint_invitation_doc_type),
        None,
    )

    additional_documents = [
        {
            "id": document.id,
            "code": document.document_type,
            "label": document.display_name,
            "source_hint": _document_source_hint(document.document_type),
        }
        for document in existing_documents
        if document.document_type not in checklist_codes and document.document_type != fingerprint_invitation_doc_type
    ]

    allow_edit = _mos_data_is_editable(mos_data)
    allow_doc_edit = _mos_documents_are_editable(mos_data)
    allow_delete = bool(mos_data and allow_doc_edit)

    case_step = session.case.get_case_step(client)

    return render(request, "clients/onboarding/start.html", {
        "session": session,
        "mos_data": mos_data,
        "checklist": checklist,
        "allow_edit": allow_edit,
        "allow_doc_edit": allow_doc_edit,
        "allow_delete": allow_delete,
        "case_step": case_step,
        "additional_documents": additional_documents,
        "fingerprint_invitation_doc_type": fingerprint_invitation_doc_type,
        "fingerprint_invitation_document": fingerprint_invitation_document,
        "fingerprint_invitation_label": client.get_document_name_by_code(fingerprint_invitation_doc_type),
        "can_change_purpose": allow_edit,
        "rejected_count": sum(1 for doc in checklist if doc.get("is_rejected")),
        "missing_case_number": bool(mos_data and mos_data.new_residence_card_application_status == 'yes' and not mos_data.new_residence_card_case_number),
        **purpose_ctx,
    })


def onboarding_purpose(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Invalid or expired onboarding link."))
    auth_redirect = check_client_auth(request, session, token)
    if auth_redirect:
        return auth_redirect
    case_redirect = check_portal_case_selected(request, session, token)
    if case_redirect:
        return case_redirect

    client = session.client
    mos_data, _created = MOSApplicationData.objects.get_or_create(client=client, case=session.case)

    if not _mos_data_is_editable(mos_data):
        return _locked_response(request, session)

    current_purpose = mos_data.mos_purpose or session.case.get_document_requirement_purpose(client)

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
    case_redirect = check_portal_case_selected(request, session, token)
    if case_redirect:
        return case_redirect

    mos_data = MOSApplicationData.objects.filter(client=session.client, case=session.case).first()
    if not _mos_documents_are_editable(mos_data):
        return _locked_response(request, session)

    if request.method == "POST":
        if not request.FILES.get("file"):
            messages.error(request, _("Выберите файл для загрузки."))
        else:
            doc_instance = Document(client=session.client, case=session.case)
            form = DocumentUploadForm(request.POST, request.FILES, doc_type=doc_type, client=session.client, case=session.case, instance=doc_instance)
            if form.is_valid():
                is_fingerprint_invitation = doc_type == DocumentType.WEZWANIE.value
                result = upload_client_document(
                    client=session.client,
                    doc_type=doc_type,
                    uploaded_document=form.save(commit=False),
                    actor=request.user if request.user.is_authenticated else None,
                    parse_requested=(doc_type == "passport"),
                    case=session.case,
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
    case_redirect = check_portal_case_selected(request, session, token)
    if case_redirect:
        return case_redirect

    document = get_object_or_404(Document, id=doc_id, client=session.client, case=session.case)
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
    case_redirect = check_portal_case_selected(request, session, token)
    if case_redirect:
        return case_redirect

    client = session.client
    mos_data = MOSApplicationData.objects.filter(client=client, case=session.case).first()

    if not _mos_documents_are_editable(mos_data):
        return _locked_response(request, session)

    doc = get_object_or_404(Document, id=doc_id, client=client, case=session.case)
    if not doc.verified:
        from clients.use_cases.documents import delete_client_document
        delete_client_document(
            document=doc,
            actor=request.user if request.user.is_authenticated else None
        )

    from django.utils.text import slugify
    return redirect(reverse("clients:onboarding_start", kwargs={"token": token}) + f"#doc-{slugify(doc.document_type)}")

def onboarding_digital_access(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))
    auth_redirect = check_client_auth(request, session, token)
    if auth_redirect:
        return auth_redirect
    case_redirect = check_portal_case_selected(request, session, token)
    if case_redirect:
        return case_redirect

    mos_data, created = MOSApplicationData.objects.get_or_create(client=session.client, case=session.case)
    if not _mos_data_is_editable(mos_data):
        return _locked_response(request, session)

    digital_access, created_access = ClientDigitalAccess.objects.defer("pesel").get_or_create(client=session.client)

    if request.method == "POST":
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
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Invalid or expired onboarding link."))
    auth_redirect = check_client_auth(request, session, token)
    if auth_redirect:
        return auth_redirect
    case_redirect = check_portal_case_selected(request, session, token)
    if case_redirect:
        return case_redirect

    client = session.client
    try:
        mos_data = MOSApplicationData.objects.get(client=client, case=session.case)
    except MOSApplicationData.DoesNotExist:
        mos_data = MOSApplicationData(client=client, case=session.case)

    if mos_data.pk and not _mos_data_is_editable(mos_data):
        return _locked_response(request, session)

    # Prefill in-memory only (without saving) for rendering form
    personal_data = dict(mos_data.personal_data or {})
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

    if request.method == "POST":
        mos_data, _created = MOSApplicationData.objects.get_or_create(client=client, case=session.case)

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
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))
    auth_redirect = check_client_auth(request, session, token)
    if auth_redirect:
        return auth_redirect
    case_redirect = check_portal_case_selected(request, session, token)
    if case_redirect:
        return case_redirect

    mos_data = get_object_or_404(MOSApplicationData, client=session.client, case=session.case)

    if not _mos_data_is_editable(mos_data):
        return _locked_response(request, session)

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
        return redirect("clients:onboarding_address", token=token)

    return render(request, "clients/onboarding/personal_extra.html", {"session": session, "mos_data": mos_data})

def onboarding_address(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))
    auth_redirect = check_client_auth(request, session, token)
    if auth_redirect:
        return auth_redirect
    case_redirect = check_portal_case_selected(request, session, token)
    if case_redirect:
        return case_redirect

    mos_data = get_object_or_404(MOSApplicationData, client=session.client, case=session.case)

    if not _mos_data_is_editable(mos_data):
        return _locked_response(request, session)

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
        return redirect("clients:onboarding_travel", token=token)

    return render(request, "clients/onboarding/address.html", {"session": session, "mos_data": mos_data})

def onboarding_travel(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))
    auth_redirect = check_client_auth(request, session, token)
    if auth_redirect:
        return auth_redirect
    case_redirect = check_portal_case_selected(request, session, token)
    if case_redirect:
        return case_redirect

    mos_data = get_object_or_404(MOSApplicationData, client=session.client, case=session.case)

    if not _mos_data_is_editable(mos_data):
        return _locked_response(request, session)

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
        return redirect("clients:onboarding_declarations", token=token)

    return render(request, "clients/onboarding/travel.html", {
        "session": session,
        "mos_data": mos_data,
        "can_change_purpose": True,
        **_purpose_context(session.client, mos_data),
    })

def onboarding_declarations(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))
    auth_redirect = check_client_auth(request, session, token)
    if auth_redirect:
        return auth_redirect
    case_redirect = check_portal_case_selected(request, session, token)
    if case_redirect:
        return case_redirect

    mos_data = get_object_or_404(MOSApplicationData, client=session.client, case=session.case)

    if not _mos_data_is_editable(mos_data):
        return _locked_response(request, session)

    if request.method == "POST":

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
    session = check_onboarding_session(token, allowed_statuses=("created", "active", "completed"), request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))
    auth_redirect = check_client_auth(request, session, token)
    if auth_redirect:
        return auth_redirect
    case_redirect = check_portal_case_selected(request, session, token)
    if case_redirect:
        return case_redirect

    mos_data = get_object_or_404(MOSApplicationData, client=session.client, case=session.case)

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

    case = None
    case_id = request.POST.get("case_id") or request.GET.get("case_id")
    if case_id:
        case = client.cases.filter(id=case_id, archived_at__isnull=True).first()
    if not case and client.cases.filter(archived_at__isnull=True).count() == 1:
        case = client.cases.filter(archived_at__isnull=True).first()

    intake_type = request.POST.get("intake_type", "").strip() if request.method == "POST" else ""
    if not intake_type:
        intake_type = "join" if (case and (case.submission_date or case.fingerprints_date)) else "new"

    token, token_hash = generate_onboarding_token()
    payment = client.payments.filter(status__in=["paid", "partial"]).first()

    with transaction.atomic():
        ClientDigitalAccess.objects.get_or_create(client=client)
        if case:
            mos_data, _created = MOSApplicationData.objects.get_or_create(client=client, case=case)
            if selected_purpose:
                # application_purpose belongs to the Case; family_role is a
                # permanent client attribute. Family purposes split into
                # application_purpose="family" + the family_role on the client.
                if selected_purpose in FAMILY_ONBOARDING_PURPOSES:
                    case.application_purpose = "family"
                    if client.family_role != selected_purpose:
                        client.family_role = selected_purpose
                        client.save(update_fields=["family_role"])
                else:
                    case.application_purpose = selected_purpose
                    if client.family_role:
                        client.family_role = ""
                        client.save(update_fields=["family_role"])
                case.save(update_fields=["application_purpose"])
                if mos_data.mos_purpose:
                    mos_data.mos_purpose = ""
                    mos_data.save(update_fields=["mos_purpose", "updated_at"])
                clear_onboarding_notifications_cache(client)
                from clients.services.activity import log_client_activity
                log_client_activity(
                    client=client,
                    case=case,
                    actor=request.user,
                    event_type="onboarding_link_purpose_set",
                    summary="Onboarding link purpose set by staff",
                    metadata={"selected_purpose": selected_purpose},
                )

            if intake_type == "join":
                mos_data.new_residence_card_application_status = "yes"
                mos_data.new_residence_card_updated_at = timezone.now()

                # Smart transition logic based on existing dates on case
                target_stage = "waiting_decision" if case.fingerprints_date else "fingerprints"
                try:
                    from clients.services.workflow_transitions import transition_case_workflow
                    transition_case_workflow(case=case, target_stage=target_stage, actor=request.user)
                    mos_data.status = target_stage
                    mos_data.save(update_fields=["new_residence_card_application_status", "new_residence_card_updated_at", "status", "updated_at"])
                except ValidationError as exc:
                    messages.error(request, str(exc))
                    return redirect("clients:client_detail", pk=client.pk)
            elif intake_type == "new":
                mos_data.new_residence_card_application_status = "no"
                mos_data.save(update_fields=["new_residence_card_application_status", "updated_at"])
        
        ClientOnboardingSession.objects.create(
            client=client,
            case=case,
            scope="case_link" if case else "client_portal",
            payment=payment,
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
                assigned_staff=request.user,
                status="new",
                workflow_stage="new_client",
            )
            finalize_client_creation(
                client=client,
                actor=request.user,
            )
            case = client.cases.order_by("opened_at", "id").first()
            mos_data, _created = MOSApplicationData.objects.get_or_create(client=client, case=case)
            if intake_type == "join":
                mos_data.new_residence_card_application_status = "yes"
                mos_data.new_residence_card_updated_at = timezone.now()
                target_stage = "fingerprints"
                try:
                    with transaction.atomic():
                        transition_client_workflow(client=client, target_stage=target_stage, actor=request.user, save=True)
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
    case_redirect = check_portal_case_selected(request, session, token)
    if case_redirect:
        return JsonResponse({"status": "redirect", "url": reverse("clients:onboarding_select_case", kwargs={"token": token})})

    client = session.client
    mos_data, created_mos = MOSApplicationData.objects.get_or_create(client=client, case=session.case)
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
    case_redirect = check_portal_case_selected(request, session, token)
    if case_redirect:
        return case_redirect

    question_text = request.POST.get("question", "").strip()
    if not question_text:
        return HttpResponseBadRequest(_("Текст вопроса не может быть пустым."))

    client = session.client

    from django.urls import reverse

    from clients.models import StaffTask

    task = StaffTask.objects.create(
        client=client,
        case=session.case,
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


def onboarding_select_case(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))
    auth_redirect = check_client_auth(request, session, token)
    if auth_redirect:
        return auth_redirect

    client = session.client
    if client.archived_at is not None:
        return render(request, "clients/onboarding/neutral.html", {"message": _("Личный кабинет недоступен.")})

    active_cases = client.cases.filter(archived_at__isnull=True)
    if not active_cases.exists():
        return render(request, "clients/onboarding/neutral.html", {"message": _("У вас нет активных дел.")})

    if request.method == "POST":
        case_id = request.POST.get("case_id")
        if case_id:
            try:
                selected_case = active_cases.get(pk=case_id)
                request.session["case_id"] = selected_case.id
                return redirect("clients:onboarding_start", token=token)
            except (Case.DoesNotExist, ValueError):
                pass

    return render(request, "clients/onboarding/select_case.html", {
        "session": session,
        "active_cases": active_cases,
    })
