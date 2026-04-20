from __future__ import annotations

import logging
import threading

from django.contrib import messages
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives, send_mail
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import override, gettext as _
from django.conf import settings
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET

from clients.models import Client, Document, EmailCampaign
from clients.services.notifications import (
    _get_preferred_language,
    _get_subject,
    _get_staff_recipients,
    _render_email_body,
    _render_email_pdf,
    _send_confirmation_email,
    _log_email,
    _get_missing_documents_context,
    _get_expiring_documents_context,
    _get_required_documents_context,
    _get_appointment_context,
)
from clients.views.base import staff_required_view

logger = logging.getLogger(__name__)

@staff_required_view
@require_GET
def email_preview_api(request, pk):
    client = get_object_or_404(Client, pk=pk)
    
    template_type = request.GET.get('template_type')
    language = request.GET.get('language') or _get_preferred_language(client)
    
    if not template_type or template_type == 'custom':
        return JsonResponse({"subject": "", "body": ""})

    context = None
    if template_type == 'missing_documents':
        context = _get_missing_documents_context(client, language)
    elif template_type == 'expiring_documents':
        documents = list(client.documents.filter(expiry_date__isnull=False))
        context = _get_expiring_documents_context(client, documents)
    elif template_type == 'required_documents':
        context = _get_required_documents_context(client, language)
    elif template_type == 'appointment_notification':
        context = _get_appointment_context(client)
    elif template_type == 'expired_documents':
        from clients.services.notifications import _get_expired_documents_context
        context = _get_expired_documents_context(client)

    if not context:
        subject = _get_subject(template_type, language)
        return JsonResponse({
            "subject": subject, 
            "body": _("Недостаточно данных у клиента для этого шаблона (например, нет даты отпечатков или списка документов).")
        })

    subject = _get_subject(template_type, language)
    body = _render_email_body(template_type, context, language)

    return JsonResponse({"subject": subject, "body": body})


@staff_required_view
@require_POST
def send_custom_email(request, pk):
    client = get_object_or_404(Client, pk=pk)
    
    if not client.email:
        messages.error(request, _("У клиента не указан email."))
        return redirect('clients:client_detail', pk=client.pk)

    # 1. Rate Limiting Check
    rate_limit = getattr(settings, 'EMAIL_RATE_LIMIT_PER_HOUR', 50)
    cache_key = f"email_rate_limit_{request.user.id}"
    sent_this_hour = cache.get(cache_key, 0)
    
    if sent_this_hour >= rate_limit:
        messages.error(request, _("Превышен лимит отправки писем (%(limit)s в час). Попробуйте позже.") % {"limit": rate_limit})
        return redirect('clients:client_detail', pk=client.pk)

    subject = request.POST.get('subject', '').strip()
    body = request.POST.get('body', '').strip()

    if not subject or not body:
        messages.error(request, _("Тема и текст письма обязательны."))
        return redirect('clients:client_detail', pk=client.pk)

    try:
        sent_count = send_mail(
            subject, 
            body, 
            settings.DEFAULT_FROM_EMAIL, 
            [client.email]
        )
        if sent_count:
            cache.set(cache_key, sent_this_hour + 1, timeout=3600)
            
            _send_confirmation_email(subject, body, [client.email])
            _log_email(
                subject, body, [client.email],
                client=client, template_type='custom', sent_by=request.user,
            )
            messages.success(request, _("Письмо '%(subject)s' успешно отправлено.") % {"subject": subject})
        else:
            messages.error(request, _("Не удалось отправить письмо (send_mail вернул 0)."))
    except Exception as e:
        logger.exception("Failed to send custom email manually")
        messages.error(request, _("Ошибка при отправке письма: %(err)s") % {"err": e})

    return redirect('clients:client_detail', pk=client.pk)


def _send_mass_email_worker(campaign_id: int, recipient_emails: list[str], subject: str, message: str):
    """Background worker that sends emails one by one and updates the campaign model."""
    try:
        campaign = EmailCampaign.objects.get(pk=campaign_id)
    except EmailCampaign.DoesNotExist:
        logger.error("EmailCampaign %s not found in worker thread", campaign_id)
        return

    campaign.status = EmailCampaign.STATUS_RUNNING
    campaign.save(update_fields=["status"])

    sent = 0
    failed = 0
    errors: list[str] = []

    for email_addr in recipient_emails:
        try:
            result = send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [email_addr],
            )
            if result:
                sent += 1
                try:
                    client = Client.objects.filter(email=email_addr).first()
                    _log_email(
                        subject, message, [email_addr],
                        client=client, template_type='mass_email',
                        sent_by=None,  # user context is not available in thread
                    )
                except Exception:
                    pass  # logging failure should not stop the campaign
            else:
                failed += 1
                errors.append(f"{email_addr}: send_mail returned 0")
        except Exception as exc:
            failed += 1
            errors.append(f"{email_addr}: {exc}")
            logger.exception("Mass email failed for %s", email_addr)

        # Update progress periodically
        campaign.sent_count = sent
        campaign.failed_count = failed
        campaign.save(update_fields=["sent_count", "failed_count"])

    # Send confirmation to admin
    try:
        _send_confirmation_email(
            f"[Массовая рассылка] {subject}",
            message,
            recipient_emails,
        )
    except Exception:
        logger.exception("Failed to send mass email confirmation")

    campaign.sent_count = sent
    campaign.failed_count = failed
    campaign.error_details = "\n".join(errors) if errors else ""
    campaign.status = EmailCampaign.STATUS_COMPLETED if not failed else EmailCampaign.STATUS_FAILED
    campaign.completed_at = timezone.now()
    campaign.save()

    logger.info(
        "Mass email campaign %s completed: sent=%d failed=%d total=%d",
        campaign_id, sent, failed, len(recipient_emails),
    )


@staff_required_view
def mass_email_view(request):
    from clients.forms import MassEmailForm
    
    if request.method == 'POST':
        form = MassEmailForm(request.POST)
        if form.is_valid():
            subject = form.cleaned_data['subject']
            message_text = form.cleaned_data['message']
            company = form.cleaned_data.get('company')
            status = form.cleaned_data.get('status')
            
            queryset = Client.objects.exclude(email='')
            if company:
                queryset = queryset.filter(company=company)
            if status:
                queryset = queryset.filter(status=status)
                
            recipient_emails = list(queryset.values_list('email', flat=True))
            if not recipient_emails:
                messages.warning(request, _("Не найдено получателей по заданным фильтрам (с указанным email)."))
                return redirect('clients:mass_email')

            # Create campaign record for tracking
            campaign = EmailCampaign.objects.create(
                subject=subject,
                message=message_text,
                total_recipients=len(recipient_emails),
                created_by=request.user,
            )

            # Launch background thread for sending
            thread = threading.Thread(
                target=_send_mass_email_worker,
                args=(campaign.id, recipient_emails, subject, message_text),
                daemon=True,
            )
            thread.start()

            messages.success(
                request,
                _("Массовая рассылка '%(subject)s' запущена (%(count)s получателей). "
                  "Статус можно отслеживать.") % {"subject": subject, "count": len(recipient_emails)},
            )
            return redirect('clients:client_list')
    else:
        form = MassEmailForm()
        
    return django_render(request, 'clients/mass_email.html', {'form': form, 'title': _('Массовая рассылка')})


@staff_required_view
@require_GET
def campaign_status_api(request, campaign_id):
    """Return the current status of a mass email campaign as JSON."""
    campaign = get_object_or_404(EmailCampaign, pk=campaign_id)
    return JsonResponse({
        "id": campaign.id,
        "subject": campaign.subject,
        "status": campaign.status,
        "status_display": campaign.get_status_display(),
        "total_recipients": campaign.total_recipients,
        "sent_count": campaign.sent_count,
        "failed_count": campaign.failed_count,
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        "completed_at": campaign.completed_at.isoformat() if campaign.completed_at else None,
    })


def django_render(request, template, context):
    from django.shortcuts import render
    return render(request, template, context)

