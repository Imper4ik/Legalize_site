from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlencode

from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import DetailView

from clients.models import AppSettings, Client, WniosekSubmission
from clients.security.encrypted import safe_encrypted_attr
from clients.services.access import accessible_clients_queryset
from clients.services.roles import DOCUMENT_EDIT_ROLES
from clients.services.wniosek import record_wniosek_submission
from clients.views.base import StaffRequiredMixin, role_required_view

if TYPE_CHECKING:
    from django.contrib.auth.models import User

class ClientPrintBaseView(StaffRequiredMixin, DetailView):
    model = Client
    context_object_name = "client"

    def get_queryset(self) -> Any:
        return accessible_clients_queryset(self.request.user, Client.objects.defer("case_number", "passport_num"))


class ClientPrintView(ClientPrintBaseView):
    template_name = "clients/client_printable.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["safe_case_number"] = safe_encrypted_attr(context["client"], "case_number")
        return context


class ClientWSCPrintView(ClientPrintBaseView):
    template_name = "clients/client_wsc_print.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["safe_case_number"] = safe_encrypted_attr(context["client"], "case_number")
        return context


class ClientDocumentPrintView(ClientPrintBaseView):
    ATTACHMENT_DEFAULT_SLOTS = 5
    ATTACHMENT_MAX_SLOTS = 15
    DEFAULT_OFFICE_LINES = [
        "Mazowiecki Urząd Wojewódzki",
        "W Warszawie",
        "Ul. Marszałkowska 3/5",
        "00-624 Warszawa",
    ]
    DEFAULT_PROXY_LINES = [
        "Ajżan Bartosik-Nisanbajewa",
        "UL. MARSZAŁKOWSKA 9/15,",
        "00-626 WARSZAWA, tel. 667066113",
        "Pełnomocnik",
    ]

    documents: dict[str, dict[str, str]] = {
        "acceleration_request": {
            "template": "clients/documents/acceleration_request.html",
        },
        "mazowiecki_application": {
            "template": "clients/documents/mazowiecki_application.html",
        },
    }

    def get_template_names(self) -> list[str]:
        doc_type = self.kwargs.get("doc_type")
        document = self.documents.get(str(doc_type))
        if not document:
            raise Http404(_("Документ не найден"))
        return [document["template"]]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["doc_type"] = self.kwargs.get("doc_type")
        if context["doc_type"] == "mazowiecki_application":
            client = context["client"]
            application_date = client.submission_date or client.created_at.date()
            attachment_names = self._get_attachment_names(client)

            # Ensure attachment_count is str or int as expected by templates
            attachment_count: str | int = self.request.GET.get("attachment_count") or ""
            if not attachment_count:
                filled_attachments = [name for name in attachment_names if name]
                attachment_count = len(filled_attachments) if filled_attachments else ""

            context.update(
                {
                    "current_date": timezone.localdate(),
                    "date_current": timezone.localdate(),
                    "application_date": application_date,
                    "full_name": f"{client.first_name} {client.last_name}",
                    "citizenship": client.citizenship or "",
                    "case_number": safe_encrypted_attr(client, "case_number"),
                    "mos_id": getattr(client, "mos_id", "") or "",
                    "inpol_id": getattr(client, "inpol_id", "") or "",
                    "birth_date": getattr(client, "birth_date", ""),
                    "attachment_count": attachment_count,
                    "attachment_names": attachment_names,
                    "office_lines": self._get_multiline_param("office_line", self.DEFAULT_OFFICE_LINES),
                    "proxy_lines": self._get_multiline_param("proxy_line", self.DEFAULT_PROXY_LINES),
                    "confirm_url": reverse_lazy(
                        "clients:client_document_print_confirm",
                        kwargs={"pk": client.pk, "doc_type": context["doc_type"]},
                    ),
                    "auto_print": self.request.GET.get("auto_print") == "1",
                    "last_submission_id": self.request.GET.get("submission_id") or "",
                    "other_text": (client.basis_of_stay or "").strip(),
                    "check_pobyt_czasowy": client.application_purpose in {"study", "work", "family"},
                    "check_pobyt_staly": False,
                    "check_rezydent_ue": False,
                    "check_uznanie_obywatel": False,
                    "check_nadanie_obywatel": False,
                    "check_swiadczenia": False,
                    "check_potwierdzenie": False,
                    "check_inne": False,
                }
            )
        return context

    def _get_attachment_names(self, client: Client) -> list[str]:
        attachments = [name.strip() for name in self.request.GET.getlist("attachments") if name.strip()]

        today = timezone.localdate()
        if client.decision_date and client.decision_date < today:
            days_overdue = (today - client.decision_date).days
            reminder_text = (
                f"Prośba o przyspieszenie wydania decyzji "
                f"(termin był {client.decision_date.strftime('%d.%m.%Y')}, {days_overdue} dni temu)"
            )
            if not any("przyspieszenie" in att.lower() for att in attachments):
                attachments.insert(0, reminder_text)

        minimum_slots = 1
        if len(attachments) < minimum_slots:
            attachments.extend([""] * (minimum_slots - len(attachments)))
        return attachments

    def _get_multiline_param(self, param_name: str, default_lines: list[str]) -> list[str]:
        values = self.request.GET.getlist(param_name)
        if not values:
            settings_attr = {
                "office_line": "mazowiecki_office_template",
                "proxy_line": "mazowiecki_proxy_template",
            }.get(param_name)
            if settings_attr:
                app_settings = AppSettings.objects.filter(pk=1).first()
                if app_settings is not None:
                    template_value = str(getattr(app_settings, settings_attr, "") or "")
                    return template_value.splitlines()
            return list(default_lines)
        return [value.strip() for value in values]


client_print_view = ClientPrintView.as_view()
client_wsc_print_view = ClientWSCPrintView.as_view()
client_document_print_view = ClientDocumentPrintView.as_view()


@role_required_view(*DOCUMENT_EDIT_ROLES)
def client_document_print_confirm_view(request: HttpRequest, pk: int, doc_type: str) -> HttpResponse:
    if request.method != "POST":
        return redirect("clients:client_document_print", pk=pk, doc_type=doc_type)

    if doc_type != WniosekSubmission.DocumentKind.MAZOWIECKI_APPLICATION:
        raise Http404("Confirmation is only available for this document type")

    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.defer("case_number", "passport_num")), pk=pk)

    # Cast user to User for record_wniosek_submission
    confirmed_by = cast('User', request.user) if request.user.is_authenticated else None

    submission = record_wniosek_submission(
        client=client,
        document_kind=doc_type,
        attachment_names=request.POST.getlist("attachments"),
        confirmed_by=confirmed_by,
        language=client.language,
    )

    confirmed_attachments = list(
        submission.attachments.order_by("position").values_list("entered_name", flat=True)
    )
    params: list[tuple[str, str]] = [("auto_print", "1"), ("submission_id", str(submission.pk))]
    for attachment_name in confirmed_attachments:
        params.append(("attachments", str(attachment_name)))
    if confirmed_attachments:
        params.append(("attachment_count", str(len(confirmed_attachments))))
    for office_line in request.POST.getlist("office_line"):
        params.append(("office_line", office_line))
    for proxy_line in request.POST.getlist("proxy_line"):
        params.append(("proxy_line", proxy_line))

    messages.success(
        request,
        _("Wniosek confirmed. Submitted attachments were saved to the client checklist."),
    )
    redirect_url = reverse_lazy("clients:client_document_print", kwargs={"pk": client.pk, "doc_type": doc_type})
    return redirect(f"{redirect_url}?{urlencode(params)}")
