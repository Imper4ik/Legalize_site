"""Staff-side onboarding entry points (link generation, quick create).

Extracted from ``onboarding_views``, which keeps the client-facing portal
views and re-exports these for URL wiring compatibility.
"""
import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from clients.models import (
    Client,
    ClientDigitalAccess,
    ClientOnboardingSession,
)
from clients.services.access import accessible_clients_queryset
from clients.services.onboarding_purposes import (
    apply_onboarding_purpose_to_case,
    apply_onboarding_purpose_to_client,
    clear_onboarding_notifications_cache,
    normalize_onboarding_purpose,
)
from clients.services.onboarding_tokens import generate_onboarding_token
from clients.services.workflow_transitions import transition_case_workflow
from clients.use_cases.client_records import finalize_client_creation
from clients.views.base import role_required_view
from clients.views.onboarding_access import (
    ONBOARDING_LINK_TTL,
    _ensure_mos,
)
from legalize_site.utils.http import request_is_ajax

logger = logging.getLogger(__name__)


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

    def _link_response() -> HttpResponse:
        if request_is_ajax(request):
            link = request.build_absolute_uri(
                reverse("clients:onboarding_start", kwargs={"token": token})
            )
            return JsonResponse({
                "status": "ok",
                "link": link,
                "message": _("Ссылка на онбординг скопирована!"),
            })
        messages.success(request, _("Ссылка на онбординг успешно создана."))
        return redirect("clients:client_detail", pk=client.id)

    # Two explicit modes (spec §5). Staff may pass a concrete case; otherwise the
    # client's single active case is used. When the case is ambiguous (zero or
    # several active cases) we never silently pick one: a client_portal link is
    # issued and the client chooses the case in the portal.
    from clients.services.cases import resolve_active_case_for_client, resolve_single_active_case

    case_uuid = request.POST.get("case_uuid") if request.method == "POST" else None
    target_case = (
        resolve_active_case_for_client(client, case_uuid)
        if case_uuid
        else resolve_single_active_case(client)
    )

    if target_case is None:
        with transaction.atomic():
            ClientDigitalAccess.objects.get_or_create(client=client)
            ClientOnboardingSession.objects.create(
                client=client,
                payment=payment,
                scope="client_portal",
                case=None,
                token_hash=token_hash,
                status="created",
                expires_at=timezone.now() + ONBOARDING_LINK_TTL,
            )
        return _link_response()

    with transaction.atomic():
        mos_data, _created = _ensure_mos(client, target_case)
        ClientDigitalAccess.objects.get_or_create(client=client)
        if selected_purpose:
            if target_case is not None:
                changed_fields = apply_onboarding_purpose_to_case(target_case, selected_purpose)
                event_type = "onboarding_link_case_purpose_set"
                summary = "Onboarding link case purpose set by staff"
            else:
                changed_fields = apply_onboarding_purpose_to_client(client, selected_purpose)
                event_type = "onboarding_link_purpose_set"
                summary = "Onboarding link purpose set by staff"
            if mos_data.mos_purpose:
                mos_data.mos_purpose = ""
                mos_data.save(update_fields=["mos_purpose", "updated_at"])
            clear_onboarding_notifications_cache(client)
            if changed_fields:
                from clients.services.activity import log_client_activity
                log_client_activity(
                    client=client,
                    case=target_case,
                    actor=request.user,
                    event_type=event_type,
                    summary=summary,
                    metadata={"changed_fields": changed_fields},
                )

        if intake_type == "join":
            mos_data.new_residence_card_application_status = "yes"
            mos_data.new_residence_card_updated_at = timezone.now()

            # Smart transition logic based on the case's existing dates (§4).
            case = mos_data.case
            if case is None:
                message = _("Не удалось определить дело для заявки.")
                if request_is_ajax(request):
                    return JsonResponse({"status": "error", "message": str(message)}, status=400)
                messages.error(request, message)
                return redirect("clients:client_detail", pk=client.pk)
            target_stage = "waiting_decision" if case.fingerprints_date else "fingerprints"
            try:
                with transaction.atomic():
                    if case.workflow_stage != target_stage:
                        transition_case_workflow(case=case, target_stage=target_stage, actor=request.user, save=True)
                    mos_data.status = target_stage
                    mos_data.save(update_fields=["new_residence_card_application_status", "new_residence_card_updated_at", "status", "updated_at"])
            except ValidationError as exc:
                # The AJAX caller must see the real validation reason instead of
                # a redirect it can only render as "failed to generate link".
                message = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
                if request_is_ajax(request):
                    return JsonResponse({"status": "error", "message": message}, status=400)
                messages.error(request, message)
                return redirect("clients:client_detail", pk=client.pk)
            except Exception:
                logger.exception("Unexpected error while preparing join onboarding", extra={"client_id": client.pk})
                message = _("Unexpected error while updating application status.")
                if request_is_ajax(request):
                    return JsonResponse({"status": "error", "message": str(message)}, status=500)
                messages.error(request, message)
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
            expires_at=timezone.now() + ONBOARDING_LINK_TTL,
        )

    return _link_response()


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
                expires_at=timezone.now() + ONBOARDING_LINK_TTL
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
