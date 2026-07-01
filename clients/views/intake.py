from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from clients.forms import ClientIntakeSubmissionForm
from clients.models import ClientIntakeSubmission, ClientOnboardingSession
from clients.services.intake import convert_intake_submission
from clients.services.onboarding_purposes import normalize_onboarding_purpose
from clients.services.onboarding_tokens import generate_onboarding_token, hash_onboarding_token
from clients.views.base import role_required_view

PUBLIC_INTAKE_LINK_TTL = timedelta(hours=72)


def _intake_from_token(token: str) -> ClientIntakeSubmission | None:
    token_hash = hash_onboarding_token(token)
    return ClientIntakeSubmission.objects.filter(token_hash=token_hash).first()


def _intake_is_closed(intake: ClientIntakeSubmission) -> bool:
    return intake.status in {
        ClientIntakeSubmission.STATUS_CONVERTED,
        ClientIntakeSubmission.STATUS_EXPIRED,
        ClientIntakeSubmission.STATUS_REVOKED,
    }


def _initial_from_intake(intake: ClientIntakeSubmission) -> dict[str, object]:
    personal = intake.personal_data if isinstance(intake.personal_data, dict) else {}
    case_data = intake.case_data if isinstance(intake.case_data, dict) else {}
    return {
        "first_name": personal.get("first_name", ""),
        "last_name": personal.get("last_name", ""),
        "email": personal.get("email", ""),
        "phone": personal.get("phone", ""),
        "birth_date": personal.get("birth_date", ""),
        "citizenship": personal.get("citizenship", ""),
        "passport_number": personal.get("document_number", ""),
        "language": personal.get("language", "pl"),
        "application_purpose": case_data.get("application_purpose", "work"),
        "application_type": case_data.get("application_type", ""),
        "basis_of_stay": case_data.get("basis_of_stay", ""),
    }


@role_required_view("Admin", "Manager", "Staff")
def create_public_intake_link(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": _("Method not allowed")}, status=405)

    try:
        selected_purpose = normalize_onboarding_purpose(request.POST.get("application_purpose", "work") or "work")
    except ValueError:
        return JsonResponse({"status": "error", "message": _("Invalid application purpose")}, status=400)

    raw_token, token_hash = generate_onboarding_token()
    ClientIntakeSubmission.objects.create(
        token_hash=token_hash,
        status=ClientIntakeSubmission.STATUS_DRAFT,
        source=ClientIntakeSubmission.SOURCE_STAFF_LINK,
        case_data={"application_purpose": selected_purpose, "workflow_stage": "new_client", "status": "new"},
        created_by=request.user if request.user.is_authenticated else None,
        expires_at=timezone.now() + PUBLIC_INTAKE_LINK_TTL,
    )
    link = request.build_absolute_uri(reverse("clients:public_intake", kwargs={"token": raw_token}))
    return JsonResponse({"status": "ok", "link": link})


def public_intake(request: HttpRequest, token: str) -> HttpResponse:
    intake = _intake_from_token(token)
    if intake is None:
        return render(request, "clients/intake/submitted.html", {"state": "invalid"}, status=404)

    if intake.expires_at is not None and intake.expires_at <= timezone.now() and not _intake_is_closed(intake):
        intake.status = ClientIntakeSubmission.STATUS_EXPIRED
        intake.save(update_fields=["status", "updated_at"])

    if intake.status in {ClientIntakeSubmission.STATUS_EXPIRED, ClientIntakeSubmission.STATUS_REVOKED}:
        return render(request, "clients/intake/submitted.html", {"state": "expired", "intake": intake}, status=403)

    if intake.status == ClientIntakeSubmission.STATUS_CONVERTED:
        return render(request, "clients/intake/submitted.html", {"state": "converted", "intake": intake})

    if request.method == "POST":
        form = ClientIntakeSubmissionForm(request.POST)
        if form.is_valid():
            User = get_user_model()
            email = form.cleaned_data["email"].strip().lower()
            existing_user = User.objects.filter(email__iexact=email).first()
            if existing_user is not None:
                if existing_user.is_staff or existing_user.is_superuser:
                    form.add_error("email", _("Этот email зарегистрирован для служебного аккаунта. Пожалуйста, используйте другой email."))
                else:
                    form.add_error("email", _("Пользователь с таким email уже зарегистрирован. Пожалуйста, войдите в систему или восстановите пароль."))
            else:
                intake.personal_data = form.personal_payload()
                intake.case_data = form.case_payload()
                intake.status = ClientIntakeSubmission.STATUS_SUBMITTED
                intake.submitted_at = timezone.now()
                intake.save(update_fields=["personal_data", "case_data", "status", "submitted_at", "updated_at"])
                try:
                    result = convert_intake_submission(intake)
                except ValidationError:
                    intake.refresh_from_db()
                    if intake.status == ClientIntakeSubmission.STATUS_NEEDS_REVIEW:
                        return render(request, "clients/intake/submitted.html", {"state": "review", "intake": intake})
                    form.add_error(None, _("We could not submit the intake form. Please check the data and try again."))
                else:
                    user = User.objects.create_user(
                        email=email,
                        password=form.password_value(),
                        first_name=form.cleaned_data["first_name"].strip(),
                        last_name=form.cleaned_data["last_name"].strip(),
                    )
                    result.client.user = user
                    result.client.save(update_fields=["user"])
                    login(request, user, backend="django.contrib.auth.backends.ModelBackend")

                    onboarding_token, onboarding_token_hash = generate_onboarding_token()
                    ClientOnboardingSession.objects.create(
                        client=result.client,
                        case=result.case,
                        scope="case_link",
                        token_hash=onboarding_token_hash,
                        status="active",
                        expires_at=timezone.now() + PUBLIC_INTAKE_LINK_TTL,
                    )
                    messages.success(request, _("Анкета отправлена. Аккаунт создан, вы вошли в личный кабинет клиента."))
                    return redirect("clients:onboarding_start", token=onboarding_token)
    else:
        form = ClientIntakeSubmissionForm(initial=_initial_from_intake(intake))

    return render(request, "clients/intake/public_form.html", {"form": form, "intake": intake})
