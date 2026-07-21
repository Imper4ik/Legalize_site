from __future__ import annotations

from collections import OrderedDict
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.core.management import call_command
from django.db.models import Count, Prefetch
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.functional import Promise
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy
from django.views.generic import ListView

from clients.constants import ACTIVE_WORKFLOW_STAGES
from clients.models import Client, ClientDocumentRequirement, Document, Reminder
from clients.services.access import accessible_clients_queryset, accessible_reminders_queryset
from clients.services.notifications import send_expiring_documents_email
from clients.services.roles import REPORT_MUTATION_ROLES
from clients.use_cases.reminders import (
    deactivate_reminder,
    delete_reminder,
    send_document_reminder_for_client,
    send_document_reminder_for_reminder,
)
from clients.views.base import StaffRequiredMixin, role_required_view

if TYPE_CHECKING:
    from django.http.response import HttpResponseBase


class ReminderListView(StaffRequiredMixin, ListView):
    model = Reminder
    context_object_name = "reminders"
    reminder_type: str | None = None
    template_name = ""
    title: str | Promise = ""
    client_param = "client"
    start_date_param = "start_date"
    end_date_param = "end_date"
    client_filter_id: int | None = None

    def get_queryset(self) -> Any:
        queryset = (
            accessible_reminders_queryset(
                self.request.user,
                Reminder.objects.filter(is_active=True, reminder_type=self.reminder_type)
            )
            .select_related("client")
            .order_by("due_date")
        )

        start_date = self.request.GET.get(self.start_date_param, "")
        if start_date:
            queryset = queryset.filter(due_date__gte=start_date)

        end_date = self.request.GET.get(self.end_date_param, "")
        if end_date:
            queryset = queryset.filter(due_date__lte=end_date)

        client_value = self.request.GET.get(self.client_param, "")
        self.client_filter_id = None
        if client_value.isdigit():
            self.client_filter_id = int(client_value)
            queryset = queryset.filter(client_id=self.client_filter_id)

        return queryset

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        reminders = context["reminders"]
        paginator = context.get("paginator")
        if paginator is not None:
            reminders_count = paginator.count
        elif hasattr(reminders, "count"):
            reminders_count = reminders.count()
        else:
            reminders_count = len(reminders)
        context.update(
            {
                "title": self.title,
                "all_clients": accessible_clients_queryset(
                    self.request.user,
                    Client.objects.filter(user__is_staff=False).order_by("created_at"),  # names encrypted
                ),
                "filter_values": self.request.GET,
                "client_filter_id": getattr(self, "client_filter_id", None),
                "reminders_count": reminders_count,
            }
        )
        return context


class DocumentReminderListView(ReminderListView):
    reminder_type = "document"
    template_name = "clients/document_reminder_list.html"
    title = _lazy("Напоминания по документам")
    client_param = "doc_client"
    start_date_param = "doc_start_date"
    end_date_param = "doc_end_date"

    @staticmethod
    def _empty_group(client: Client) -> dict[str, Any]:
        return {
            "client": client,
            "reminders": [],
            "documents": [],
            "missing_documents": [],
            "expired_count": 0,
            "soon_count": 0,
            "ok_count": 0,
            "status_class": "success",
        }

    def _missing_document_clients_queryset(self) -> Any:
        # Active = the client has at least one active (non-finished) case (§4).
        queryset = Client.objects.filter(
            cases__workflow_stage__in=ACTIVE_WORKFLOW_STAGES
        ).distinct().order_by(
            "last_name",
            "first_name",
        )
        queryset = accessible_clients_queryset(self.request.user, queryset)
        client_filter_id = getattr(self, "client_filter_id", None)
        if client_filter_id:
            queryset = queryset.filter(pk=client_filter_id)
        return queryset.prefetch_related(
            Prefetch(
                "documents",
                queryset=Document.objects.annotate(preloaded_version_count=Count("versions")).order_by("-uploaded_at"),
            ),
            Prefetch(
                "custom_document_requirements",
                queryset=ClientDocumentRequirement.objects.filter(is_active=True).order_by("due_date", "created_at"),
            ),
            "wniosek_submissions__confirmed_by",
            "wniosek_submissions__attachments",
        )

    @staticmethod
    def _missing_documents_for_client(client: Client, requirements_cache: dict[str, Any]) -> list[dict[str, Any]]:
        checklist = client.get_document_checklist(requirements_cache=requirements_cache) or []
        return [
            {
                "name": item.get("name"),
                "expiry_date": getattr((item.get("documents") or [None])[0], "expiry_date", None),
            }
            for item in checklist
            if not item.get("is_complete")
        ]

    def get_queryset(self) -> Any:
        return (
            super()
            .get_queryset()
            .select_related("document")
            .prefetch_related(
                Prefetch(
                    "client__documents",
                    queryset=Document.objects.annotate(preloaded_version_count=Count("versions")).order_by("-uploaded_at"),
                ),
                Prefetch(
                    "client__custom_document_requirements",
                    queryset=ClientDocumentRequirement.objects.filter(is_active=True).order_by("due_date", "created_at"),
                ),
                "client__wniosek_submissions__confirmed_by",
                "client__wniosek_submissions__attachments",
            )
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        reminders = list(context["reminders"])
        missing_only = self.request.GET.get("view") == "missing"
        grouped: OrderedDict[int, dict[str, Any]] = OrderedDict()
        today = timezone.localdate()
        soon_cutoff = today + timedelta(days=3)
        for reminder in reminders:
            client = reminder.client
            group = grouped.setdefault(client.id, self._empty_group(client))
            group["reminders"].append(reminder)
            if reminder.document and reminder.document.expiry_date:
                group["documents"].append(reminder.document)
            if reminder.due_date:
                if reminder.due_date < today:
                    group["expired_count"] += 1
                elif reminder.due_date < soon_cutoff:
                    group["soon_count"] += 1
                else:
                    group["ok_count"] += 1

        requirements_cache: dict[str, Any] = {}
        for group in grouped.values():
            group["missing_documents"] = self._missing_documents_for_client(group["client"], requirements_cache)

        if missing_only:
            for client in self._missing_document_clients_queryset():
                group = grouped.setdefault(client.id, self._empty_group(client))
                if group["missing_documents"]:
                    continue
                group["missing_documents"] = self._missing_documents_for_client(client, requirements_cache)

        for group in grouped.values():
            if group["expired_count"]:
                group["status_class"] = "danger"
            elif group["soon_count"]:
                group["status_class"] = "warning"
            elif group["missing_documents"]:
                group["status_class"] = "secondary"
            else:
                group["status_class"] = "success"

        grouped_reminders = list(grouped.values())
        total_missing_documents_count = sum(len(group["missing_documents"]) for group in grouped_reminders)
        missing_clients_count = sum(1 for group in grouped_reminders if group["missing_documents"])
        if missing_only:
            grouped_reminders = [group for group in grouped_reminders if group["missing_documents"]]
        display_count = total_missing_documents_count if missing_only else len(grouped_reminders)

        context.update(
            {
                "grouped_reminders": grouped_reminders,
                "missing_only": missing_only,
                "reminders_count": display_count,
                "total_reminders_count": len(reminders),
                "total_missing_documents_count": total_missing_documents_count,
                "missing_clients_count": missing_clients_count,
            }
        )
        return context


class PaymentReminderListView(ReminderListView):
    reminder_type = "payment"
    template_name = "clients/payment_reminder_list.html"
    title = _lazy("Напоминания по оплатам")
    # Payment reminders render one card per row with no client grouping, so a
    # large active caseload previously loaded every reminder into a single
    # page. Paginate to bound the query volume and page weight.
    paginate_by = 50

    def get_queryset(self) -> Any:
        # display_title / display_notes for a payment reminder read the related
        # payment (amount_due, service description) on every row. Join it up
        # front so the page stays at a constant query count regardless of how
        # many reminders are shown, instead of one extra query per row.
        return super().get_queryset().select_related("payment")


UPDATE_REMINDERS_LOCK_KEY = "manual_update_reminders_lock"


@role_required_view(*REPORT_MUTATION_ROLES)
def run_update_reminders(request: HttpRequest) -> HttpResponseBase:
    if request.method == "POST":
        from django.core.cache import cache

        # Serialize manual runs: the command walks every active case/document/
        # payment and sends emails, so a double-click or a run overlapping the
        # cron contour must not start a second pass. Idempotency keys make a
        # duplicate pass mostly harmless, but it still burns worker time.
        if not cache.add(UPDATE_REMINDERS_LOCK_KEY, timezone.now().isoformat(), timeout=15 * 60):
            messages.warning(request, _("Проверка напоминаний уже выполняется. Попробуйте позже."))
        else:
            try:
                call_command("update_reminders")
                messages.success(request, _("Проверка завершена. Новые напоминания, если были найдены, успешно созданы!"))
            except Exception as e:
                messages.error(request, _("Произошла ошибка при создании напоминаний: %(err)s") % {"err": e})
            finally:
                cache.delete(UPDATE_REMINDERS_LOCK_KEY)
        next_page = request.POST.get("next", "documents")
        if next_page == "payments":
            return redirect("clients:payment_reminder_list")
        return redirect("clients:document_reminder_list")

    messages.warning(request, _("Эту операцию можно выполнить только через специальную кнопку."))
    return redirect("clients:document_reminder_list")


@role_required_view(*REPORT_MUTATION_ROLES)
def reminder_action(request: HttpRequest, reminder_id: int) -> HttpResponseBase:
    reminder = get_object_or_404(accessible_reminders_queryset(request.user, Reminder.objects.all()), pk=reminder_id)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            delete_reminder(reminder=reminder, actor=request.user)
            messages.success(request, _("Напоминание удалено."))
        elif action == "deactivate":
            deactivate_reminder(reminder=reminder, actor=request.user)
            messages.success(request, _("Напоминание отмечено как выполненное."))
        elif action == "send_email" and reminder.reminder_type == "document":
            result = send_document_reminder_for_reminder(
                reminder=reminder,
                actor=request.user,
                send_email=send_expiring_documents_email,
            )
            if result.email_sent:
                messages.success(request, _("Отправили письмо клиенту об истекающем документе."))
            else:
                messages.warning(request, _("Не удалось отправить письмо: нет email или даты истечения."))

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
    if next_url and not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = None
    return redirect(next_url or "clients:document_reminder_list")


@role_required_view(*REPORT_MUTATION_ROLES)
def send_document_reminder_email(request: HttpRequest, client_id: int) -> HttpResponseBase:
    if request.method == "POST":
        client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=client_id)
        result = send_document_reminder_for_client(
            client=client,
            actor=request.user,
            send_email=send_expiring_documents_email,
        )
        if result.email_sent:
            messages.success(request, _("Отправили письмо клиенту по документам."))
        else:
            messages.warning(request, _("Не удалось отправить письмо: нет email или документов с датой истечения."))
        next_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
        if next_url and not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            next_url = None
        return redirect(next_url or "clients:document_reminder_list")

    messages.warning(request, _("Эту операцию можно выполнить только через кнопку отправки."))
    return redirect("clients:document_reminder_list")
