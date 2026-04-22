from __future__ import annotations

import logging

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from django.utils.translation import gettext as _

from clients.models import Client, EmailCampaign
from clients.services.access import accessible_campaigns_queryset, accessible_clients_queryset
from clients.services.email_campaigns import queue_mass_email_campaign
from clients.services.notifications import (
    _get_appointment_context,
    _get_expiring_documents_context,
    _get_missing_documents_context,
    _get_preferred_language,
    _get_required_documents_context,
    _get_subject,
    _log_email,
    _render_email_body,
    _send_confirmation_email,
    build_email_idempotency_key,
)
from clients.services.responses import json_no_store
from clients.views.base import staff_required_view

logger = logging.getLogger(__name__)


@staff_required_view
@require_GET
def email_preview_api(request, pk):
    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=pk)

    template_type = request.GET.get("template_type")
    language = request.GET.get("language") or _get_preferred_language(client)

    if not template_type or template_type == "custom":
        return json_no_store({"subject": "", "body": ""})

    context = None
    if template_type == "missing_documents":
        context = _get_missing_documents_context(client, language)
    elif template_type == "expiring_documents":
        documents = list(client.documents.filter(expiry_date__isnull=False))
        context = _get_expiring_documents_context(client, documents)
    elif template_type == "required_documents":
        context = _get_required_documents_context(client, language)
    elif template_type == "appointment_notification":
        context = _get_appointment_context(client)
    elif template_type == "expired_documents":
        from clients.services.notifications import _get_expired_documents_context

        context = _get_expired_documents_context(client)

    if not context:
        subject = _get_subject(template_type, language)
        return json_no_store(
            {
                "subject": subject,
                "body": _(
                    "Недостаточно данных у клиента для этого шаблона "
                    "(например, нет даты отпечатков или списка документов)."
                ),
            }
        )

    subject = _get_subject(template_type, language)
    body = _render_email_body(template_type, context, language)
    return json_no_store({"subject": subject, "body": body})


@staff_required_view
@require_POST
def send_custom_email(request, pk):
    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=pk)

    if not client.email:
        messages.error(request, _("У клиента не указан email."))
        return redirect("clients:client_detail", pk=client.pk)

    rate_limit = getattr(settings, "EMAIL_RATE_LIMIT_PER_HOUR", 50)
    cache_key = f"email_rate_limit_{request.user.id}"
    sent_this_hour = cache.get(cache_key, 0)

    if sent_this_hour >= rate_limit:
        messages.error(
            request,
            _("Превышен лимит отправки писем (%(limit)s в час). Попробуйте позже.")
            % {"limit": rate_limit},
        )
        return redirect("clients:client_detail", pk=client.pk)

    subject = request.POST.get("subject", "").strip()
    body = request.POST.get("body", "").strip()

    if not subject or not body:
        messages.error(request, _("Тема и текст письма обязательны."))
        return redirect("clients:client_detail", pk=client.pk)

    try:
        idempotency_key = build_email_idempotency_key(
            "custom_email",
            request.user.pk,
            client.pk,
            client.email,
            subject,
            body,
        )
        from clients.models import EmailLog

        if EmailLog.objects.filter(
            idempotency_key=idempotency_key,
            delivery_status=EmailLog.DELIVERY_STATUS_SENT,
        ).exists():
            messages.info(request, _("Такое письмо уже было отправлено. Повторная отправка пропущена."))
            return redirect("clients:client_detail", pk=client.pk)

        sent_count = send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [client.email],
        )
        if sent_count:
            cache.set(cache_key, sent_this_hour + 1, timeout=3600)

            _send_confirmation_email(subject, body, [client.email])
            _log_email(
                subject,
                body,
                [client.email],
                client=client,
                template_type="custom",
                sent_by=request.user,
                idempotency_key=idempotency_key,
                delivery_status="sent",
            )
            messages.success(request, _("Письмо '%(subject)s' успешно отправлено.") % {"subject": subject})
        else:
            messages.error(request, _("Не удалось отправить письмо (send_mail вернул 0)."))
    except Exception as e:  # pragma: no cover - defensive safeguard
        logger.exception("Failed to send custom email manually")
        messages.error(request, _("Ошибка при отправке письма: %(err)s") % {"err": e})

    return redirect("clients:client_detail", pk=client.pk)


@staff_required_view
def mass_email_view(request):
    from clients.forms import MassEmailForm

    if request.method == "POST":
        form = MassEmailForm(request.POST)
        if form.is_valid():
            subject = form.cleaned_data["subject"]
            message_text = form.cleaned_data["message"]
            company = form.cleaned_data.get("company")
            status = form.cleaned_data.get("status")

            queryset = accessible_clients_queryset(
                request.user,
                Client.objects.exclude(email__isnull=True).exclude(email__exact=""),
            )
            if company:
                queryset = queryset.filter(company=company)
            if status:
                queryset = queryset.filter(status=status)

            filters_snapshot = {
                "company_id": company.pk if company else None,
                "company_label": str(company) if company else "",
                "status": status or "",
            }

            try:
                campaign = queue_mass_email_campaign(
                    subject=subject,
                    message=message_text,
                    recipient_emails=queryset.values_list("email", flat=True),
                    created_by=request.user,
                    filters_snapshot=filters_snapshot,
                )
            except ValueError:
                messages.warning(
                    request,
                    _("Не найдено получателей по заданным фильтрам (с указанным email)."),
                )
                return redirect("clients:mass_email")

            logger.info(
                "Queued mass email campaign %s by user=%s recipients=%s filters=%s",
                campaign.pk,
                request.user.pk,
                campaign.total_recipients,
                campaign.filters_snapshot,
            )
            messages.success(
                request,
                _(
                    "Кампания #%(id)s поставлена в очередь (%(count)s получателей). "
                    "Статус можно отслеживать на панели администратора."
                )
                % {"id": campaign.pk, "count": campaign.total_recipients},
            )
            return redirect("clients:client_list")
    else:
        form = MassEmailForm()

    return render(request, "clients/mass_email.html", {"form": form, "title": _("Массовая рассылка")})


@staff_required_view
@require_GET
def campaign_status_api(request, campaign_id):
    campaign = get_object_or_404(
        accessible_campaigns_queryset(request.user, EmailCampaign.objects.all()),
        pk=campaign_id,
    )
    return json_no_store(
        {
            "id": campaign.id,
            "subject": campaign.subject,
            "status": campaign.status,
            "status_display": campaign.get_status_display(),
            "total_recipients": campaign.total_recipients,
            "sent_count": campaign.sent_count,
            "failed_count": campaign.failed_count,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
            "started_at": campaign.started_at.isoformat() if campaign.started_at else None,
            "completed_at": campaign.completed_at.isoformat() if campaign.completed_at else None,
            "error_details": campaign.error_details,
            "filters_snapshot": campaign.filters_snapshot,
            "created_by": getattr(campaign.created_by, "email", None),
        }
    )
