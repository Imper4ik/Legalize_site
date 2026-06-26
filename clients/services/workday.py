from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, cast

from django.db.models import Count, Prefetch, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from clients.constants import ACTIVE_WORKFLOW_STAGES, FINISHED_WORKFLOW_STAGES, DocumentType
from clients.models import Case, Client, ClientDocumentRequirement, Document, Payment, StaffTask
from clients.services.access import (
    accessible_cases_queryset,
    accessible_clients_queryset,
    accessible_documents_queryset,
    accessible_payments_queryset,
    accessible_tasks_queryset,
)
from clients.services.zus import format_zus_months, missing_zus_months

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

FINGERPRINTS_FOLLOWUP_DAYS = 90


def _client_url(client_id: int, anchor: str = "") -> str:
    return f"{reverse('clients:client_detail', kwargs={'pk': client_id})}{anchor}"


def _section(key: str, title: str, description: str, icon: str, items: list[dict[str, Any]], action_url: str = "") -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "description": description,
        "icon": icon,
        "items": items,
        "count": len(items),
        "action_url": action_url,
    }


def _review_documents(user: AbstractBaseUser | AnonymousUser | None, limit: int) -> list[dict[str, Any]]:
    today = timezone.localdate()
    queryset = (
        accessible_documents_queryset(
            user,
            Document.objects.select_related("client").filter(archived_at__isnull=True),
        )
        .filter(Q(verified=False) | Q(awaiting_confirmation=True))
        .exclude(Q(rejection_reason__isnull=False) & ~Q(rejection_reason=""))
        .exclude(expiry_date__isnull=False, expiry_date__lt=today)
        .order_by("uploaded_at")[:limit]
    )
    return [
        {
            "client": document.client,
            "title": document.display_name,
            "detail": document.uploaded_at,
            "url": reverse("clients:document_preview", kwargs={"doc_id": document.pk}),
            "action_label": _("Проверить"),
            "document_type": document.document_type,
        }
        for document in queryset
    ]


def _missing_document_clients(user: AbstractBaseUser | AnonymousUser | None, limit: int) -> list[dict[str, Any]]:
    candidates = (
        accessible_clients_queryset(
            user,
            Client.objects.filter(
                cases__workflow_stage__in=ACTIVE_WORKFLOW_STAGES
            ).distinct().order_by("last_name", "first_name"),
        )
        .prefetch_related(
            Prefetch("documents", queryset=Document.objects.order_by("-uploaded_at")),
            Prefetch(
                "custom_document_requirements",
                queryset=ClientDocumentRequirement.objects.filter(is_active=True).order_by("due_date", "created_at"),
            ),
            "wniosek_submissions__confirmed_by",
            "wniosek_submissions__attachments",
        )[:50]
    )
    items: list[dict[str, Any]] = []
    requirements_cache: dict[str, Any] = {}
    for client in candidates:
        missing = [item for item in client.get_document_checklist(requirements_cache=requirements_cache) if not item.get("is_complete")]
        if not missing:
            continue
        items.append(
            {
                "client": client,
                "title": _("Недостающие документы"),
                "detail": ", ".join(str(item.get("name")) for item in missing[:3]),
                "extra_count": max(len(missing) - 3, 0),
                "url": _client_url(client.pk, "#documentAccordion"),
                "action_label": _("Открыть чеклист"),
            }
        )
        if len(items) >= limit:
            break
    return items


def _missing_zus_clients(user: AbstractBaseUser | AnonymousUser | None, today: date, limit: int) -> list[dict[str, Any]]:
    # Case-first: iterate active cases (archived cases are excluded by the
    # default manager) and read ZUS process data from the case.
    candidates = accessible_cases_queryset(
        user,
        Case.objects.select_related("client").filter(
            workflow_stage="waiting_decision",
            fingerprints_date__isnull=False,
            decision_date__isnull=True,
        ).order_by("fingerprints_date"),
    )[:50]
    items: list[dict[str, Any]] = []
    for case in candidates:
        months = missing_zus_months(case, today=today)
        if not months:
            continue
        items.append(
            {
                "client": case.client,
                "title": _("ZUS RCA"),
                "detail": format_zus_months(months),
                "url": _client_url(case.client_id, "#documentAccordion"),
                "action_label": _("Запросить"),
            }
        )
        if len(items) >= limit:
            break
    return items


def _new_card_missing_case(user: AbstractBaseUser | AnonymousUser | None, limit: int) -> list[dict[str, Any]]:
    # Case-first (spec §5/§6): iterate the per-case MOS records so a client with
    # two qualifying cases surfaces once per case, each with its own submission
    # data, instead of an arbitrary ``mos_applications.first()``.
    from clients.models import MOSApplicationData

    accessible_cases = accessible_cases_queryset(user)
    mos_queryset = (
        MOSApplicationData.objects.filter(
            case__in=accessible_cases,
            new_residence_card_application_status="yes",
        )
        .filter(
            Q(case__authority_case_number_hash__isnull=True) | Q(case__authority_case_number_hash="")
        )
        .select_related("case", "case__client")
        .annotate(
            new_card_confirmation_count=Count(
                "case__documents",
                filter=Q(
                    case__documents__document_type=DocumentType.NEW_RESIDENCE_CARD_APPLICATION_CONFIRMATION.value,
                    case__documents__archived_at__isnull=True,
                ),
                distinct=True,
            )
        )
        .order_by(
            "new_residence_card_submitted_at",
            "case__client__last_name",
            "case__client__first_name",
        )
    )[:limit]
    items: list[dict[str, Any]] = []
    for mos_data in mos_queryset:
        # case is non-null: the queryset filters case__in=accessible_cases.
        client = cast("Case", mos_data.case).client
        detail_parts = []
        if mos_data.new_residence_card_submitted_at:
            detail_parts.append(mos_data.new_residence_card_submitted_at.strftime("%d.%m.%Y"))
        detail_parts.append(_("подтверждение загружено") if mos_data.new_card_confirmation_count else _("нет подтверждения"))
        if str(mos_data.new_residence_card_case_number or "").strip():
            detail_parts.append(_("номер есть в блоке подачи"))
        items.append(
            {
                "client": client,
                "title": _("Новая подача без основного номера"),
                "detail": " · ".join(str(part) for part in detail_parts),
                "url": _client_url(client.pk, "#new-card-application-summary"),
                "action_label": _("Проверить подачу"),
            }
        )
    return items


def _fingerprints_followup(user: AbstractBaseUser | AnonymousUser | None, today: date, limit: int) -> list[dict[str, Any]]:
    cutoff = today - timedelta(days=FINGERPRINTS_FOLLOWUP_DAYS)
    queryset = accessible_cases_queryset(
        user,
        Case.objects.select_related("client").filter(
            fingerprints_date__isnull=False,
            fingerprints_date__lte=cutoff,
            decision_date__isnull=True,
        )
        .exclude(workflow_stage__in=["closed", "decision_received"])
        .order_by("fingerprints_date"),
    )[:limit]
    return [
        {
            "client": case.client,
            "title": _("После отпечатков без решения"),
            "detail": _("%(days)s дней после отпечатков") % {"days": (today - cast(date, case.fingerprints_date)).days},
            "url": _client_url(case.client_id, "#overview"),
            "action_label": _("Проверить статус"),
        }
        for case in queryset
    ]


def _overdue_tasks(user: AbstractBaseUser | AnonymousUser | None, today: date, limit: int) -> list[dict[str, Any]]:
    queryset = (
        accessible_tasks_queryset(user, StaffTask.objects.select_related("client", "assignee"))
        .filter(status__in=["open", "in_progress"], due_date__lt=today)
        .order_by("due_date", "-created_at")[:limit]
    )
    return [
        {
            "client": task.client,
            "title": task.title,
            "detail": _("срок: %(date)s") % {"date": cast(date, task.due_date).strftime("%d.%m.%Y")},
            "url": task.communication_url,
            "action_label": _("Открыть"),
        }
        for task in queryset
    ]


def _overdue_payments(user: AbstractBaseUser | AnonymousUser | None, today: date, limit: int) -> list[dict[str, Any]]:
    queryset = (
        accessible_payments_queryset(user, Payment.objects.select_related("client"))
        .filter(status__in=["pending", "partial"], due_date__isnull=False, due_date__lte=today, archived_at__isnull=True)
        .order_by("due_date", "-created_at")[:limit]
    )
    return [
        {
            "client": payment.client,
            "title": payment.get_service_description_display(),
            "detail": _("к оплате: %(amount)s PLN") % {"amount": payment.amount_due},
            "url": _client_url(payment.client_id, "#payment-list-container"),
            "action_label": _("Открыть финансы"),
        }
        for payment in queryset
    ]


def _is_stay_expiring_soon(client: Client, today: date) -> bool:
    # Only fall back to MOS data when the client has a single active case; with
    # several cases we do not guess which legal-stay date applies (spec §4/§5).
    from clients.services.cases import resolve_single_active_case

    case = resolve_single_active_case(client)
    if case is not None and case.workflow_stage in FINISHED_WORKFLOW_STAGES:
        return False
    date_to_check = client.legal_basis_end_date
    if not date_to_check and case is not None:
        mos_data = client.mos_applications.filter(case=case).first()
        if mos_data:
            date_to_check = mos_data.legal_stay_until
    if date_to_check:
        return date_to_check <= today + timedelta(days=30)
    return False


def _determine_priority(key: str, item: dict[str, Any], today: date) -> str:
    client = item.get("client")
    if client and _is_stay_expiring_soon(client, today):
        return "urgent"

    if key == "overdue_tasks":
        return "urgent"

    if key == "documents_review":
        doc_type = item.get("document_type")
        if doc_type == DocumentType.WEZWANIE.value:
            return "urgent"
        return "important"

    if key in ("missing_documents", "zus_rca"):
        return "important"

    return "other"


def build_workday_context(
    user: AbstractBaseUser | AnonymousUser | None,
    *,
    today: date | None = None,
    limit_per_section: int = 8,
) -> dict[str, Any]:
    today = today or timezone.localdate()
    sections = [
        _section(
            "documents_review",
            _("Документы на проверку"),
            _("Новые загрузки и OCR-данные, которые сотрудник ещё не подтвердил."),
            "bi-file-earmark-check",
            _review_documents(user, limit_per_section),
            reverse("clients:client_list") + "?attention=unverified_documents",
        ),
        _section(
            "missing_documents",
            _("Недостающие документы"),
            _("Клиенты, у которых ещё не закрыт обязательный чеклист."),
            "bi-folder-x",
            _missing_document_clients(user, limit_per_section),
            reverse("clients:document_reminder_list") + "?view=missing#documents-section",
        ),
        _section(
            "zus_rca",
            _("ZUS RCA"),
            _("Дела после отпечатков, где не хватает актуальных ZUS RCA."),
            "bi-file-medical",
            _missing_zus_clients(user, today, limit_per_section),
        ),
        _section(
            "new_card_missing_case",
            _("Новая подача без номера дела"),
            _("Клиент сообщил о подаче, но основной номер дела в карточке ещё пуст."),
            "bi-file-earmark-plus",
            _new_card_missing_case(user, limit_per_section),
            reverse("clients:client_list") + "?attention=new_card_missing_case",
        ),
        _section(
            "fingerprints_followup",
            _("После отпечатков без решения"),
            _("Прошло больше 90 дней после отпечатков, решения в карточке нет."),
            "bi-fingerprint",
            _fingerprints_followup(user, today, limit_per_section),
            reverse("clients:fingerprints_schedule"),
        ),
        _section(
            "overdue_tasks",
            _("Просроченные задачи"),
            _("Открытые задачи сотрудников с прошедшим сроком."),
            "bi-list-task",
            _overdue_tasks(user, today, limit_per_section),
            reverse("clients:task_list"),
        ),
        _section(
            "overdue_payments",
            _("Платежи"),
            _("Просроченные или частично оплаченные счета."),
            "bi-credit-card-2-back",
            _overdue_payments(user, today, limit_per_section),
            reverse("clients:payment_reminder_list"),
        ),
    ]

    urgent_count = 0
    important_count = 0
    other_count = 0

    for section in sections:
        for item in section["items"]:
            priority = _determine_priority(section["key"], item, today)
            item["priority"] = priority
            if priority == "urgent":
                urgent_count += 1
            elif priority == "important":
                important_count += 1
            else:
                other_count += 1

    # Group by client
    priority_order = {"urgent": 3, "important": 2, "other": 1}
    clients_map: dict[Any, dict[str, Any]] = {}

    for section in sections:
        section_key = section["key"]
        section_title = section["title"]
        for item in section["items"]:
            client = item["client"]

            icons = {
                "documents_review": "bi-file-earmark-check",
                "missing_documents": "bi-folder-x",
                "zus_rca": "bi-file-medical",
                "new_card_missing_case": "bi-file-earmark-plus",
                "fingerprints_followup": "bi-fingerprint",
                "overdue_tasks": "bi-list-task",
                "overdue_payments": "bi-credit-card-2-back",
            }

            alert = {
                "section_key": section_key,
                "section_title": section_title,
                "title": item["title"],
                "detail": item.get("detail"),
                "url": item["url"],
                "action_label": item.get("action_label") or _("Открыть"),
                "priority": item["priority"],
                "icon": icons.get(section_key, "bi-exclamation-circle"),
            }

            clients_map.setdefault(client.pk, {"client": client, "alerts": []})
            clients_map[client.pk]["alerts"].append(alert)

    client_list = []
    for client_id, data in clients_map.items():
        highest_p = "other"
        highest_p_val = 0
        for alert in data["alerts"]:
            p = alert["priority"]
            val = priority_order.get(p, 0)
            if val > highest_p_val:
                highest_p_val = val
                highest_p = p
        data["highest_priority"] = highest_p
        client_list.append(data)

    client_list.sort(key=lambda d: (-priority_order.get(d["highest_priority"], 0), str(d["client"])))

    total_items = sum(section["count"] for section in sections)
    return {
        "today": today,
        "workday_sections": sections,
        "workday_clients": client_list,
        "workday_total_items": total_items,
        "has_workday_items": total_items > 0,
        "urgent_count": urgent_count,
        "important_count": important_count,
        "other_count": other_count,
    }
