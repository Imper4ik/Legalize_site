from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string

from clients.forms import PaymentForm
from clients.models import Client, Payment
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
            if helper.expects_json:
                html = render_to_string('clients/partials/payment_item.html', {'payment': payment})
                return helper.success(html=html, payment_id=payment.id)
            messages.success(request, "Платёж успешно добавлен.")
            return redirect('clients:client_detail', pk=client.id)
        if helper.expects_json:
            return helper.error(
                message='Проверьте правильность заполнения формы.',
                errors=form.errors,
            )

    return redirect('clients:client_detail', pk=client.id)


@staff_required_view
def edit_payment(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    helper = ResponseHelper(request)
    if request.method == 'POST':
        form = PaymentForm(request.POST, instance=payment)
        if form.is_valid():
            payment = form.save()
            if helper.expects_json:
                html = render_to_string('clients/partials/payment_item.html', {'payment': payment})
                return helper.success(html=html, payment_id=payment.id)
            messages.success(request, "Платёж успешно обновлён.")
            return redirect('clients:client_detail', pk=payment.client.id)
        if helper.expects_json:
            return helper.error(
                message='Проверьте правильность заполнения формы.',
                errors=form.errors,
            )

    return redirect('clients:client_detail', pk=payment.client.id)


@staff_required_view
def delete_payment(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    client_id = payment.client.id
    helper = ResponseHelper(request)
    if request.method == 'POST':
        payment.delete()
        if helper.expects_json:
            return helper.success()
        messages.success(request, "Платёж успешно удалён.")
    return redirect('clients:client_detail', pk=client_id)


@staff_required_view
def get_price_for_service(request, service_value):
    price = get_service_price(service_value)
    helper = ResponseHelper(request)
    return helper.success(price=price)
