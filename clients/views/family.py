from __future__ import annotations

from typing import Any, TYPE_CHECKING

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views import View

from clients.forms import FamilyGroupFinanceForm
from clients.models import Client
from clients.services.access import accessible_clients_queryset
from clients.services.family import (
    calculate_family_income,
    ensure_family_group,
    family_sponsor_for,
    get_existing_family_group,
    get_family_members,
)
from clients.views.base import StaffRequiredMixin

if TYPE_CHECKING:
    from clients.models import FamilyGroup


class FamilyDashboardView(StaffRequiredMixin, View):
    template_name = "clients/family_dashboard.html"

    def _get_sponsor(self, pk: int) -> Client:
        client = get_object_or_404(accessible_clients_queryset(self.request.user, Client.objects.all()), pk=pk)
        sponsor = family_sponsor_for(client)
        return get_object_or_404(accessible_clients_queryset(self.request.user, Client.objects.all()), pk=sponsor.pk)

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        sponsor = self._get_sponsor(pk)
        group = get_existing_family_group(sponsor)
        return render(request, self.template_name, self._context(sponsor, group))

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        sponsor = self._get_sponsor(pk)
        group = ensure_family_group(sponsor)
        form = FamilyGroupFinanceForm(request.POST, instance=group)
        if form.is_valid():
            form.save()
            messages.success(request, _("Финансовая достаточность обновлена."))
            return redirect("clients:family_dashboard", pk=sponsor.pk)
        return render(request, self.template_name, self._context(sponsor, group, form=form), status=400)

    def _context(self, sponsor: Client, group: FamilyGroup | None, *, form: FamilyGroupFinanceForm | None = None) -> dict[str, Any]:
        group_obj = group or self._empty_family_group(sponsor)
        members = list(get_family_members(sponsor))
        person_cards = [
            self._person_card(sponsor, role_label=str(_("Спонсор"))),
            *[
                self._person_card(member, role_label=str(member.get_family_role_display()))
                for member in members
            ],
        ]
        total_missing_documents = sum(card["missing_documents_count"] for card in person_cards)
        income = calculate_family_income(group_obj)

        family_risks = list(income.risks)
        if total_missing_documents:
            family_risks.append(
                {
                    "title": _("Не все документы собраны"),
                    "message": _("Отсутствует обязательных документов: %(count)s.")
                    % {"count": total_missing_documents},
                }
            )

        return {
            "sponsor": sponsor,
            "members": members,
            "person_cards": person_cards,
            "family_group": group_obj,
            "finance_form": form or FamilyGroupFinanceForm(instance=group_obj),
            "income": income,
            "family_risks": family_risks,
            "housing_note": _("Бесплатное жильё требует подтверждения.")
            if income.housing_confirmation_required
            else "",
        }

    def _person_card(self, client: Client, *, role_label: str) -> dict[str, Any]:
        checklist = client.get_document_checklist(check_file_existence=False)
        missing_documents_count = sum(1 for item in checklist if not item.get("is_complete"))
        return {
            "client": client,
            "role_label": role_label,
            "missing_documents_count": missing_documents_count,
            "open_url": reverse("clients:client_detail", kwargs={"pk": client.pk}),
            "documents_url": reverse("clients:client_detail", kwargs={"pk": client.pk}) + "#documentAccordion",
            "finances_url": reverse("clients:client_detail", kwargs={"pk": client.pk}) + "#payment-list-container",
        }

    @staticmethod
    def _empty_family_group(sponsor: Client) -> FamilyGroup:
        from clients.models import FamilyGroup

        return FamilyGroup(sponsor=sponsor)
