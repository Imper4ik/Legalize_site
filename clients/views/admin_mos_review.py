from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import HttpRequest, HttpResponse

from clients.models import Client, MOSApplicationData

@login_required
def admin_mos_review(request: HttpRequest, client_id: int) -> HttpResponse:
    client = get_object_or_404(Client, id=client_id)
    mos_data = get_object_or_404(MOSApplicationData, client=client)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve":
            mos_data.status = "mos_package_ready"
            mos_data.staff_reviewed_at = timezone.now()
            mos_data.staff_reviewed_by = request.user
            mos_data.save()
            messages.success(request, "Анкета утверждена. Пакет MOS готов.")
            return redirect("clients:client_detail", pk=client.id)
        elif action == "request_correction":
            mos_data.status = "needs_correction"
            mos_data.correction_message = request.POST.get("correction_message", "")
            mos_data.save()
            messages.warning(request, "Запрошено исправление у клиента.")
            return redirect("clients:client_detail", pk=client.id)
        elif action == "mark_submitted":
            mos_data.status = "submitted_in_mos"
            mos_data.save()
            messages.success(request, "Статус: Подано в MOS.")
            return redirect("clients:admin_mos_review", client_id=client.id)
        elif action == "mark_fingerprints":
            mos_data.status = "fingerprints"
            mos_data.save()
            messages.success(request, "Статус: Отпечатки сданы.")
            return redirect("clients:admin_mos_review", client_id=client.id)
        elif action == "mark_waiting":
            mos_data.status = "waiting_decision"
            mos_data.save()
            messages.success(request, "Статус: Ожидание решения.")
            return redirect("clients:admin_mos_review", client_id=client.id)
        elif action == "mark_decision":
            mos_data.status = "decision_received"
            mos_data.save()
            messages.success(request, "Статус: Децизия получена.")
            return redirect("clients:admin_mos_review", client_id=client.id)

    return render(request, "clients/mos_review.html", {"client": client, "mos_data": mos_data})
