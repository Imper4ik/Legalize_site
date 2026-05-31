from __future__ import annotations

from typing import Any, TYPE_CHECKING

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Max, Prefetch, Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from clients.forms import (
    ClientForm,
    DocumentUploadForm,
    PaymentForm,
    StaffTaskForm,
)
from clients.models import Client, ClientActivity, Document, EmailLog, Payment, StaffTask, WniosekSubmission
from clients.services.notifications import (
    send_expired_documents_email,
    send_required_documents_email,
)
from clients.services.zus import missing_zus_month_upload_options
from clients.services.responses import apply_no_store
from clients.services.roles import (
    CLIENT_DELETE_ROLES,
    user_has_any_role,
)
from clients.use_cases.client_records import (
    finalize_client_creation,
    finalize_client_update,
    snapshot_client_update_state,
)
from clients.views.base import RoleOrFeatureRequiredMixin, RoleRequiredMixin, StaffRequiredMixin, role_required_view
from clients.services.activity import log_client_view
from clients.services.access import accessible_clients_queryset

if TYPE_CHECKING:
    from django.http.response import HttpResponseBase


def _show_family_dashboard_link(client: Client) -> bool:
    return bool(
        client.family_role
        or client.sponsor_client_id
        or client.application_purpose in {"family", "family_spouse", "family_child"}
        or client.sponsored_family_members.exists()
    )


class ClientListView(StaffRequiredMixin, ListView):
    model = Client
    template_name = "clients/clients_list.html"
    context_object_name = "clients"
    paginate_by = 15

    def get_queryset(self) -> Any:
        queryset = accessible_clients_queryset(
            self.request.user,
            Client.objects.filter(Q(user__is_staff=False) | Q(user__isnull=True)),
        ).select_related("sponsor_client", "mos_application_data").annotate(
            family_members_count=Count("sponsored_family_members")
        )

        list_ordering = ["-created_at"]
        self.onboarding_filter = self.request.GET.get("onboarding", "")
        if self.onboarding_filter:
            if self.onboarding_filter == "completed":
                queryset = queryset.filter(mos_application_data__status="client_completed")
                list_ordering = ["-mos_application_data__updated_at", "-created_at"]
            elif self.onboarding_filter in ["staff_review", "submitted_in_mos"]:
                queryset = queryset.filter(mos_application_data__status=self.onboarding_filter)
                list_ordering = ["-mos_application_data__updated_at", "-created_at"]

        self.document_filter = self.request.GET.get("document", "")
        if self.document_filter == "ocr_review":
            queryset = queryset.filter(
                documents__awaiting_confirmation=True,
                documents__archived_at__isnull=True,
            )
            queryset = queryset.annotate(latest_event_uploaded_at=Max("documents__uploaded_at"))
            list_ordering = ["-latest_event_uploaded_at", "-created_at"]
        elif self.document_filter == "ocr_warning":
            queryset = queryset.filter(
                documents__ocr_name_mismatch=True,
                documents__archived_at__isnull=True,
            )
            queryset = queryset.annotate(latest_event_uploaded_at=Max("documents__uploaded_at"))
            list_ordering = ["-latest_event_uploaded_at", "-created_at"]
        elif self.document_filter == "ocr_pending":
            queryset = queryset.filter(
                documents__ocr_status="pending",
                documents__archived_at__isnull=True,
            )
            queryset = queryset.annotate(latest_event_uploaded_at=Max("documents__uploaded_at"))
            list_ordering = ["-latest_event_uploaded_at", "-created_at"]

        company_id = self.request.GET.get("company")
        if company_id:
            queryset = queryset.filter(company_id=company_id)

        query = self.request.GET.get("q", "")
        if query:
            case_number_hash = Client.hash_case_number(query)
            queryset = queryset.filter(
                Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
                | Q(phone__icontains=query)
                | Q(case_number_hash=case_number_hash)
            )
        return queryset.distinct().order_by(*list_ordering)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        from clients.models import Company

        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "")
        context["selected_company"] = self.request.GET.get("company", "")
        context["onboarding_filter"] = self.request.GET.get("onboarding", "")
        context["document_filter"] = self.request.GET.get("document", "")
        context["companies"] = Company.objects.all()
        return context


class ClientDetailView(StaffRequiredMixin, DetailView):
    model = Client
    template_name = "clients/client_detail.html"

    def get_queryset(self) -> Any:
        return accessible_clients_queryset(
            self.request.user,
            Client.objects.select_related("user", "sponsor_client", "company", "assigned_staff").prefetch_related(
                Prefetch("payments", queryset=Payment.objects.order_by("-created_at")),
                Prefetch(
                    "documents",
                    queryset=Document.objects.annotate(
                        preloaded_version_count=Count("versions")
                    ).order_by("-uploaded_at"),
                ),
                Prefetch(
                    "staff_tasks",
                    queryset=StaffTask.objects.select_related("assignee", "created_by").order_by(
                        "status",
                        "due_date",
                        "-created_at",
                    ),
                ),
                Prefetch(
                    "activities",
                    queryset=ClientActivity.objects.select_related("actor", "document", "payment", "task").order_by(
                        "-created_at"
                    ),
                ),
                Prefetch("email_logs", queryset=EmailLog.objects.select_related("sent_by").order_by("-sent_at")),
                Prefetch(
                    "wniosek_submissions",
                    queryset=WniosekSubmission.objects.select_related("confirmed_by")
                    .prefetch_related("attachments")
                    .order_by("-confirmed_at"),
                ),
                "reminders",
                "sponsored_family_members",
            ),
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        client = self.object
        document_status_list = client.get_document_checklist(check_file_existence=True) if hasattr(client, "get_document_checklist") else []

        context["payment_form"] = PaymentForm()
        context["document_upload_form"] = DocumentUploadForm()
        context["document_status_list"] = document_status_list
        context["missing_zus_months_for_upload"] = missing_zus_month_upload_options(client)
        prefetched = getattr(client, "_prefetched_objects_cache", {})
        email_logs = prefetched.get("email_logs")
        if email_logs is None:
            email_logs = client.email_logs.select_related("sent_by").order_by("-sent_at")
        context["email_logs"] = email_logs[:50]
        context["service_choices"] = Payment.SERVICE_CHOICES
        context["task_form"] = StaffTaskForm(initial={"assignee": self.request.user.pk})
        staff_tasks = prefetched.get("staff_tasks")
        if staff_tasks is None:
            open_tasks = client.staff_tasks.filter(
                status__in=["open", "in_progress"],
            ).select_related("assignee", "created_by")
        else:
            open_tasks = [task for task in staff_tasks if task.status in {"open", "in_progress"}]
        context["open_tasks"] = open_tasks[:10]
        context["recent_activities"] = client.activities.all()[:25]
        context["workflow_summary"] = client.get_workflow_summary(document_status_list=document_status_list)
        context["workflow_alerts"] = context["workflow_summary"]["alerts"]
        context["show_family_dashboard_link"] = _show_family_dashboard_link(client)
        context["family_dashboard_url"] = reverse("clients:family_dashboard", kwargs={"pk": client.pk})
        return context

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        self.object = self.get_object()
        log_client_view(client=self.object, actor=request.user, request=request)
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)


class ClientCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = ["Admin", "Manager", "Staff"]
    model = Client
    form_class = ClientForm
    template_name = "clients/client_form.html"
    success_url = reverse_lazy("clients:client_list")

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial() or {}
        sponsor_id = self.request.GET.get("sponsor")
        if not sponsor_id:
            return initial
        try:
            sponsor_pk = int(sponsor_id)
        except (TypeError, ValueError):
            raise Http404("Sponsor not found")

        sponsor = accessible_clients_queryset(self.request.user, Client.objects.all()).filter(pk=sponsor_pk).first()
        if sponsor is None:
            raise Http404("Sponsor not found")

        initial["application_purpose"] = "family"
        initial["sponsor_client"] = sponsor.pk
        return initial

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = str(_("Добавить нового клиента"))
        return context

    def form_valid(self, form: ClientForm) -> HttpResponse:
        if not form.instance.assigned_staff_id:
            form.instance.assigned_staff = self.request.user
        messages.success(self.request, _("Клиент успешно добавлен!"))
        with transaction.atomic():
            self.object = form.save()
            finalize_client_creation(
                client=self.object,
                actor=self.request.user,
                send_required_email=send_required_documents_email,
            )
        return redirect(self.get_success_url())

    def form_invalid(self, form: ClientForm) -> HttpResponse:
        messages.error(
            self.request,
            _("Не удалось сохранить клиента. Проверьте выделенные поля и попробуйте снова."),
        )
        return super().form_invalid(form)


class ClientUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = ["Admin", "Manager", "Staff"]
    model = Client
    form_class = ClientForm
    template_name = "clients/client_form.html"

    def get_queryset(self) -> Any:
        return accessible_clients_queryset(self.request.user, Client.objects.all())

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_success_url(self) -> str:
        return str(reverse_lazy("clients:client_detail", kwargs={"pk": self.object.pk}))

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = str(_("Редактировать данные клиента"))
        return context

    def form_valid(self, form: ClientForm) -> HttpResponse:
        previous_fingerprints_date = self.object.fingerprints_date
        previous_values = snapshot_client_update_state(self.object)
        messages.success(self.request, _("Данные клиента успешно обновлены!"))
        with transaction.atomic():
            self.object = form.save()
            finalize_client_update(
                client=self.object,
                actor=self.request.user,
                previous_values=previous_values,
                previous_fingerprints_date=previous_fingerprints_date,
                new_fingerprints_date=form.cleaned_data.get("fingerprints_date"),
                send_expired_email=send_expired_documents_email,
            )
        return redirect(self.get_success_url())

    def form_invalid(self, form: ClientForm) -> HttpResponse:
        messages.error(
            self.request,
            _("Не удалось сохранить клиента. Проверьте выделенные поля и попробуйте снова."),
        )
        return super().form_invalid(form)


class ClientDeleteView(RoleOrFeatureRequiredMixin, DeleteView):
    allowed_roles = list(CLIENT_DELETE_ROLES)
    required_permission_name = "can_delete_clients"
    model = Client
    template_name = "clients/client_confirm_delete.html"
    success_url = reverse_lazy("clients:client_list")

    def get_queryset(self) -> Any:
        return accessible_clients_queryset(self.request.user, Client.objects.all())

    def form_valid(self, form: Any) -> HttpResponse:
        client_name = self.get_object()
        messages.success(self.request, _("Клиент %(name)s был успешно удалён.") % {"name": client_name})
        return super().form_valid(form)


def dashboard_redirect_view(request: HttpRequest) -> HttpResponseBase:
    if not request.user.is_authenticated:
        return redirect("account_login")

    if user_has_any_role(request.user, "Admin", "Manager", "Staff", "ReadOnly"):
        return redirect("clients:client_list")
    if user_has_any_role(request.user, "Translator") and getattr(settings, "ENABLE_TRANSLATION_TOOLING", False):
        return redirect("translations:dashboard")

    support_email = str(getattr(settings, "DEFAULT_FROM_EMAIL", "support@example.com"))
    context = {
        "support_email": support_email,
        "error_title": _("Доступ запрещен"),
    }
    return render(request, "403.html", context=context, status=403)


def calculator_view(request: HttpRequest) -> HttpResponseBase:
    from clients.forms import CalculatorForm
    from clients.services.calculator import (
        LIVING_ALLOWANCE,
        MAX_MONTHS_LIVING,
        calculate_calculator_result,
        get_eur_to_pln_rate,
    )

    form = CalculatorForm(request.POST or None)
    form_data: dict[str, Any] = {}
    result = None
    if request.method == "POST":
        if form.is_valid():
            result = calculate_calculator_result(form.cleaned_data)
            form_data = form.cleaned_data
        else:
            form_data = dict(form.data)
            messages.error(request, _("Ошибка. Пожалуйста, заполните все поля корректными значениями."))

    context = {
        "living_allowance": result.living_allowance if result else LIVING_ALLOWANCE,
        "eur_to_pln_rate": float(get_eur_to_pln_rate()),
        "max_months_living": MAX_MONTHS_LIVING,
        "form": form,
        "form_data": form_data,
        "results": result,
    }

    response = render(request, "clients/calculator.html", context)
    return apply_no_store(response)


@role_required_view("Admin", "Manager", "Staff")
def client_autocomplete_api(request: HttpRequest) -> HttpResponse:
    from django.http import JsonResponse
    from django.db.models import Q
    from clients.models import Client
    from clients.services.access import accessible_clients_queryset

    query = request.GET.get("q", "").strip()
    if not query or len(query) < 2:
        return JsonResponse({"results": []})

    queryset = accessible_clients_queryset(
        request.user,
        Client.objects.filter(Q(user__is_staff=False) | Q(user__isnull=True))
    )

    case_number_hash = Client.hash_case_number(query)
    queryset = queryset.filter(
        Q(first_name__icontains=query)
        | Q(last_name__icontains=query)
        | Q(email__icontains=query)
        | Q(phone__icontains=query)
        | Q(case_number_hash=case_number_hash)
    )

    results = []
    for client in queryset.distinct()[:8]:
        results.append({
            "id": client.id,
            "first_name": client.first_name,
            "last_name": client.last_name,
            "email": client.email or "",
            "phone": client.phone or "",
            "url": reverse("clients:client_detail", kwargs={"pk": client.id})
        })

    return JsonResponse({"results": results})
