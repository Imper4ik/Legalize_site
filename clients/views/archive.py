from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _

from clients.models import Client, Document, Payment
from clients.services.access import (
    accessible_clients_queryset,
    accessible_documents_queryset,
    accessible_payments_queryset,
)
from clients.use_cases.archive import (
    restore_client_document,
    restore_client_payment,
    restore_client_record,
)
from clients.views.base import role_required_view


@role_required_view("Admin", "Manager")
def restore_client_view(request, pk):
    if request.method != "POST":
        return redirect("clients:client_list")

    client = get_object_or_404(
        accessible_clients_queryset(request.user, Client.all_objects.all()),
        pk=pk,
        archived_at__isnull=False,
    )
    restore_client_record(client=client, actor=request.user)
    messages.success(request, _("Клиент восстановлен из архива."))
    return redirect("clients:client_detail", pk=client.pk)


@role_required_view("Admin", "Manager")
def restore_document_view(request, pk):
    if request.method != "POST":
        return redirect("clients:client_list")

    document = get_object_or_404(
        accessible_documents_queryset(request.user, Document.all_objects.select_related("client")),
        pk=pk,
        archived_at__isnull=False,
    )
    result = restore_client_document(document=document, actor=request.user)
    messages.success(request, _("Документ восстановлен из архива."))
    return redirect("clients:client_detail", pk=result.client.pk)


@role_required_view("Admin", "Manager")
def restore_payment_view(request, pk):
    if request.method != "POST":
        return redirect("clients:client_list")

    payment = get_object_or_404(
        accessible_payments_queryset(request.user, Payment.all_objects.select_related("client")),
        pk=pk,
        archived_at__isnull=False,
    )
    result = restore_client_payment(payment=payment, actor=request.user)
    messages.success(request, _("Платёж восстановлен из архива."))
    return redirect("clients:client_detail", pk=result.client.pk)
