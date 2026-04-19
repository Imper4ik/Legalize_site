from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils.translation import gettext as _

from clients.forms import PaymentForm
from clients.models import Client, Payment
from clients.services.activity import changed_field_labels, log_client_activity
from clients.services.pricing import get_service_price
from clients.services.responses import ResponseHelper
from clients.views.base import staff_required_view


@staff_required_view
def add_payment(request, client_id):
    client = get_object_or_404(Client, pk=client_id)
    helper = ResponseHelper(request)
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.client = client
            payment.save()
            log_client_activity(
                client=client,
                actor=request.user,
                event_type="payment_created",
                summary=f"Создан платёж: {payment.get_service_description_display()}",
                metadata={
                    "payment_id": payment.id,
                    "status": payment.status,
                    "total_amount": str(payment.total_amount),
                },
                payment=payment,
            )
            if helper.expects_json:
                html = render_to_string('clients/partials/payment_item.html', {'payment': payment})
                return helper.success(html=html, payment_id=payment.id)
            messages.success(request, _("Платёж успешно добавлен."))
            return redirect('clients:client_detail', pk=client.id)
        if helper.expects_json:
            return helper.error(
                message=_('Проверьте правильность заполнения формы.'),
                errors=form.errors,
            )

    return redirect('clients:client_detail', pk=client.id)


@staff_required_view
def edit_payment(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    helper = ResponseHelper(request)
    if request.method == 'POST':
        tracked_fields = [
            "service_description",
            "total_amount",
            "amount_paid",
            "status",
            "payment_method",
            "payment_date",
            "due_date",
            "transaction_id",
        ]
        previous_values = {field: getattr(payment, field) for field in tracked_fields}
        form = PaymentForm(request.POST, instance=payment)
        if form.is_valid():
            payment = form.save()
            changed_fields = [field for field, old_value in previous_values.items() if getattr(payment, field) != old_value]
            if changed_fields:
                log_client_activity(
                    client=payment.client,
                    actor=request.user,
                    event_type="payment_updated",
                    summary=f"Обновлён платёж: {payment.get_service_description_display()}",
                    details=", ".join(changed_field_labels(payment, changed_fields)),
                    metadata={"payment_id": payment.id, "changed_fields": changed_fields},
                    payment=payment,
                )
            if helper.expects_json:
                html = render_to_string('clients/partials/payment_item.html', {'payment': payment})
                return helper.success(html=html, payment_id=payment.id)
            messages.success(request, _("Платёж успешно обновлён."))
            return redirect('clients:client_detail', pk=payment.client.id)
        if helper.expects_json:
            return helper.error(
                message=_('Проверьте правильность заполнения формы.'),
                errors=form.errors,
            )

    return redirect('clients:client_detail', pk=payment.client.id)


@staff_required_view
def delete_payment(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    client_id = payment.client.id
    helper = ResponseHelper(request)
    if request.method == 'POST':
        log_client_activity(
            client=payment.client,
            actor=request.user,
            event_type="payment_deleted",
            summary=f"Удалён платёж: {payment.get_service_description_display()}",
            metadata={"payment_id": payment.id, "status": payment.status},
        )
        payment.delete()
        if helper.expects_json:
            return helper.success()
        messages.success(request, _("Платёж успешно удалён."))
    return redirect('clients:client_detail', pk=client_id)


@staff_required_view
def get_price_for_service(request, service_value):
    price = get_service_price(service_value)
    helper = ResponseHelper(request)
    return helper.success(price=price)
