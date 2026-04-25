from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils.translation import gettext as _

from clients.forms import PaymentForm
from clients.models import Client, Payment
from clients.services.access import accessible_clients_queryset, accessible_payments_queryset
from clients.services.pricing import get_service_price
from clients.services.responses import ResponseHelper
from clients.use_cases.payments import (
    create_payment_for_client,
    delete_payment_for_client,
    update_payment_for_client,
)
from clients.services.roles import PAYMENT_MUTATION_ROLES
from clients.views.base import role_required_view


@role_required_view(*PAYMENT_MUTATION_ROLES)
def add_payment(request, client_id):
    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=client_id)
    helper = ResponseHelper(request)
    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            result = create_payment_for_client(
                client=client,
                actor=request.user,
                cleaned_data=form.cleaned_data,
            )
            payment = result.payment
            if helper.expects_json:
                html = render_to_string("clients/partials/payment_item.html", {"payment": payment})
                return helper.success(
                    message=_("Платёж успешно добавлен."),
                    html=html,
                    payment_id=payment.id,
                )
            messages.success(request, _("Платёж успешно добавлен."))
            return redirect("clients:client_detail", pk=client.id)
        if helper.expects_json:
            return helper.error(
                message=_("Проверьте правильность заполнения формы."),
                errors=form.errors,
            )

    return redirect("clients:client_detail", pk=client.id)


@role_required_view(*PAYMENT_MUTATION_ROLES)
def edit_payment(request, payment_id):
    payment = get_object_or_404(accessible_payments_queryset(request.user, Payment.objects.all()), pk=payment_id)
    helper = ResponseHelper(request)
    if request.method == "POST":
        form = PaymentForm(request.POST, instance=payment)
        if form.is_valid():
            result = update_payment_for_client(
                payment=payment,
                actor=request.user,
                cleaned_data=form.cleaned_data,
            )
            updated_payment = result.payment
            if helper.expects_json:
                html = render_to_string("clients/partials/payment_item.html", {"payment": updated_payment})
                return helper.success(
                    message=_("Платёж успешно обновлён."),
                    html=html,
                    payment_id=updated_payment.id,
                )
            messages.success(request, _("Платёж успешно обновлён."))
            return redirect("clients:client_detail", pk=updated_payment.client.id)
        if helper.expects_json:
            return helper.error(
                message=_("Проверьте правильность заполнения формы."),
                errors=form.errors,
            )

    return redirect("clients:client_detail", pk=payment.client.id)


@role_required_view(*PAYMENT_MUTATION_ROLES)
def delete_payment(request, payment_id):
    payment = get_object_or_404(accessible_payments_queryset(request.user, Payment.objects.all()), pk=payment_id)
    client_id = payment.client.id
    helper = ResponseHelper(request)
    if request.method == "POST":
        delete_payment_for_client(payment=payment, actor=request.user)
        if helper.expects_json:
            return helper.success(message=_("Платёж успешно удалён."))
        messages.success(request, _("Платёж успешно удалён."))
    return redirect("clients:client_detail", pk=client_id)


@role_required_view(*PAYMENT_MUTATION_ROLES)
def get_price_for_service(request, service_value):
    price = get_service_price(service_value)
    helper = ResponseHelper(request)
    return helper.success(price=price)
