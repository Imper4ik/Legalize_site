"""Onboarding session, auth and MOS-scoping helpers.

Extracted from ``onboarding_views``; shared by the portal step views
(``onboarding_step_return``, ``onboarding_start_contact``) and the client
document views that stayed in the facade.
"""
import logging
from datetime import timedelta
from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import (
    HttpRequest,
    HttpResponse,
    JsonResponse,
)
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from clients.constants import SELF_ONBOARDING_SLUG, DocumentType
from clients.models import (
    Case,
    Client,
    ClientDigitalAccess,
    ClientOnboardingSession,
    MOSApplicationData,
)
from clients.services.case_context import working_purpose_for_case
from clients.services.onboarding_purposes import (
    clear_onboarding_notifications_cache,
    purpose_label,
)
from clients.services.onboarding_tokens import hash_onboarding_token
from legalize_site.utils.http import request_is_ajax

EDITABLE_MOS_STATUSES = {"draft", "client_filling", "needs_correction"}
CONTACT_SYNC_FIELDS = ("first_name", "last_name", "phone", "email")
logger = logging.getLogger(__name__)

# Emailed onboarding links carry a raw bearer token in the URL. Keep their
# lifetime short to bound the replay window if a link leaks via history, a
# forwarded message, or logs (audit Q-1). The authenticated ``me`` portal
# session is not an emailed token link and keeps a longer, separate lifetime.
ONBOARDING_LINK_TTL = timedelta(hours=72)




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


def _get_effective_document_purpose(
    client: Client,
    mos_data: MOSApplicationData | None = None,
    case: Case | None = None,
) -> str:
    if case is not None:
        return working_purpose_for_case(case, mos_data)
    return client.get_document_requirement_purpose()


def _purpose_context(
    client: Client,
    mos_data: MOSApplicationData | None,
    case: Case | None = None,
) -> dict[str, str | bool]:
    effective_purpose = _get_effective_document_purpose(client, mos_data, case)
    client_selected_purpose = mos_data.mos_purpose if mos_data else ""
    original_client_purpose = getattr(case, "application_purpose", client.application_purpose)
    return {
        "effective_purpose": effective_purpose,
        "client_selected_purpose": client_selected_purpose,
        "original_client_purpose": original_client_purpose,
        "effective_purpose_label": purpose_label(effective_purpose),
        "client_selected_purpose_label": purpose_label(client_selected_purpose),
        "original_client_purpose_label": purpose_label(effective_purpose),
        "purpose_mismatch": bool(client_selected_purpose and client_selected_purpose != effective_purpose),
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
    if session.scope != "client_portal" or _session_case(session) is not None:
        return None
    # When the client has exactly one active case there is nothing to choose, so
    # auto-select it instead of forcing the picker. This is safe: the
    # ownership/archive re-validation in check_onboarding_session still runs on
    # every request, and the picker is still shown for several active cases
    # (spec §5). With zero active cases the picker shows the empty state.
    active_cases = list(Case.objects.filter(client=session.client)[:2])
    if len(active_cases) == 1:
        request.session["case_id"] = active_cases[0].id
        session.active_case = active_cases[0]  # type: ignore[attr-defined]
        return None
    return redirect("clients:onboarding_select_case", token=token)


def _ensure_mos(client: Client, case: Any = None) -> tuple[MOSApplicationData, bool]:
    """Create/fetch the MOS record for a specific case (spec §8).

    MOS data is always scoped to a Case, never the bare Client. When the caller
    already knows the case it is used directly; otherwise the client's single
    active case is resolved. A client with zero or several active cases is
    ambiguous, so this raises instead of guessing or creating a case-less MOS.
    """
    from django.core.exceptions import ValidationError

    from clients.services.cases import resolve_single_active_case

    resolved_case = case or resolve_single_active_case(client)
    if resolved_case is None:
        raise ValidationError("Для этой операции необходимо выбрать дело.")
    return MOSApplicationData.objects.get_or_create(client=client, case=resolved_case)


def _get_scoped_mos(session: ClientOnboardingSession) -> MOSApplicationData | None:
    """Return the MOS record for the session's active case, or None.

    Strictly case-scoped (spec §8): without a case in scope there is no MOS to
    show, so this returns ``None`` rather than falling back to an arbitrary
    client-level record that could belong to another case.
    """
    case = _session_case(session)
    if case is None:
        return None
    return MOSApplicationData.objects.filter(client=session.client, case=case).first()


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
            # Self-onboarding is strictly a client_portal session. Filter by scope
            # so an older case_link session (bound to a specific case) is never
            # picked up as the portal session (spec §5).
            session = ClientOnboardingSession.objects.filter(
                client=client,
                scope="client_portal",
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
        request.session["prefilled_email"] = client.email
        return redirect(login_url)

    return None


def check_client_auth_token_link(
    request: HttpRequest, session: ClientOnboardingSession, token: str
) -> HttpResponse | None:
    """Always require authentication/login/password setup, even for raw tokens."""
    return check_client_auth(request, session, token)


def _validate_portal_email(email: str, client: Client) -> str | None:
    try:
        validate_email(email)
    except ValidationError:
        return str(_("Введите корректный адрес электронной почты."))

    expected_email = str(client.email or "").strip().casefold()
    if expected_email and email.casefold() != expected_email:
        return str(_("Email должен совпадать с адресом, указанным для этой ссылки. Если адрес неверный, обратитесь в офис."))
    return None


def _split_onboarding_full_name(full_name: str) -> tuple[str, str] | None:
    parts = full_name.split()
    if len(parts) < 2:
        return None
    return " ".join(parts[1:]), parts[0]


def _mark_user_email_verified(user: Any, email: str) -> None:
    from allauth.account.models import EmailAddress

    # The email is globally unique in allauth. A stale row may still point at
    # an account that has since changed its email away (staff typo fixes); the
    # address must follow its rightful current owner instead of crashing
    # account creation with a UNIQUE error.
    email_address, _created = EmailAddress.objects.update_or_create(
        email__iexact=email,
        defaults={"user": user, "email": email, "primary": True, "verified": True},
    )

    EmailAddress.objects.filter(user=user).exclude(pk=email_address.pk).update(primary=False)


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
