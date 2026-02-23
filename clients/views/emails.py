from __future__ import annotations

import logging
from django.contrib import messages
from django.core.mail import EmailMultiAlternatives
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import override
from django.conf import settings
from django.views.decorators.http import require_POST, require_GET

from clients.models import Client, Document
from clients.services.notifications import (
    _get_preferred_language,
    _get_subject,
    _get_staff_recipients,
    _render_email_body,
    _render_email_pdf,
    _send_confirmation_email,
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
        context = _get_missing_documents_context(client)
    elif template_type == 'expiring_documents':
        # Need documents for expiring, grab all with expiry date for preview
        documents = list(client.documents.filter(expiry_date__isnull=False))
        context = _get_expiring_documents_context(client, documents)
    elif template_type == 'required_documents':
        context = _get_required_documents_context(client)
    elif template_type == 'appointment_notification':
        context = _get_appointment_context(client)
    elif template_type == 'expired_documents':
        from clients.services.notifications import _get_expired_documents_context
        context = _get_expired_documents_context(client)

    if not context:
        subject = _get_subject(template_type, language)
        return JsonResponse({
            "subject": subject, 
            "body": f"Недостаточно данных у клиента для этого шаблона (например, нет даты отпечатков или списка документов)."
        })

    subject = _get_subject(template_type, language)
    body = _render_email_body(template_type, context, language)

    return JsonResponse({"subject": subject, "body": body})


@staff_required_view
@require_POST
def send_custom_email(request, pk):
    client = get_object_or_404(Client, pk=pk)
    
    if not client.email:
        messages.error(request, "У клиента не указан email.")
        return redirect('clients:client_detail', pk=client.pk)

    subject = request.POST.get('subject', '').strip()
    body = request.POST.get('body', '').strip()

    if not subject or not body:
        messages.error(request, "Тема и текст письма обязательны.")
        return redirect('clients:client_detail', pk=client.pk)

    try:
        from django.core.mail import send_mail
        sent_count = send_mail(
            subject, 
            body, 
            settings.DEFAULT_FROM_EMAIL, 
            [client.email]
        )
        if sent_count:
            _send_confirmation_email(subject, body, [client.email])
            messages.success(request, f"Письмо '{subject}' успешно отправлено.")
        else:
            messages.error(request, "Не удалось отправить письмо (send_mail вернул 0).")
    except Exception as e:
        logger.exception("Failed to send custom email manually")
        messages.error(request, f"Ошибка при отправке письма: {e}")

    return redirect('clients:client_detail', pk=client.pk)
