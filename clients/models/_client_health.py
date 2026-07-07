from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from clients.constants import DocumentType

if TYPE_CHECKING:
    from clients.models import Client

# RODO art. 12(3): the controller must respond to a data-subject request (incl.
# erasure, art. 17) "without undue delay and in any event within one month" of
# receipt. We track that statutory clock so staff act before it is breached.
RODO_ERASURE_RESPONSE_DAYS = 30
# Start warning one week before the deadline so there is time to act.
RODO_ERASURE_WARNING_LEAD_DAYS = 7


def _erasure_deadline_state(client: "Client", today: Any) -> tuple[str, int] | None:
    """Return (severity, days_left) for a pending erasure request, or None.

    ``days_left`` is negative once the statutory one-month deadline has passed.
    Returns None when there is no open request (never requested, or already
    fulfilled), so callers only surface the check when it is actionable.
    """
    requested_at = getattr(client, "erasure_requested_at", None)
    if requested_at is None or getattr(client, "erasure_fulfilled_at", None) is not None:
        return None
    deadline = timezone.localtime(requested_at).date() + timedelta(days=RODO_ERASURE_RESPONSE_DAYS)
    days_left = (deadline - today).days
    if days_left < 0:
        return "danger", days_left
    if days_left <= RODO_ERASURE_WARNING_LEAD_DAYS:
        return "warning", days_left
    return "info", days_left


def build_health_alerts(client: "Client", document_status_list: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    today = timezone.localdate()

    # Process state lives on the case (spec §4): read the case number and
    # fingerprints date from the single active case, not the legacy mirror.
    from clients.services.cases import resolve_single_active_case

    active_case = resolve_single_active_case(client)
    effective_case_number = (
        (active_case.authority_case_number if active_case is not None else "") or ""
    )
    effective_fingerprints_date = (
        active_case.fingerprints_date if active_case is not None else None
    )

    stats = (
        cast(Any, client.__class__.objects).filter(pk=client.pk)
        .with_health_stats(today=today)
        .values(
            "health_awaiting_confirmation_count",
            "health_expired_documents_count",
            "health_expiring_documents_count",
            "health_wezwanie_count",
            "health_appointment_email_sent_count",
            "health_overdue_payments_count",
            "health_overdue_tasks_count",
        )
        .get()
    )
    for key, value in stats.items():
        setattr(client, key, value)

    # Check legal stay expiration only before submission: once the case is
    # submitted to the urząd the stamp legalises the stay (spec/business rule).
    if client.get_effective_workflow_stage() in ["new_client", "document_collection"] and not client.has_submitted_case:
        legal_stay_date = client.legal_basis_end_date or client._get_mos_legal_stay_until()

        if legal_stay_date:
            if legal_stay_date < today:
                alerts.append(
                    {
                        "level": "danger",
                        "title": _("Основание пребывания уже истекло"),
                        "message": _("Проверьте основание пребывания и свяжитесь с клиентом."),
                        "action_label": _("Связаться с клиентом"),
                        "action_url": "#history",
                    }
                )
            elif legal_stay_date <= today + timedelta(days=30):
                alerts.append(
                    {
                        "level": "warning",
                        "title": _("Основание пребывания скоро истекает"),
                        "message": _("До окончания основания пребывания осталось меньше 30 дней."),
                        "action_label": _("Связаться с клиентом"),
                        "action_url": "#history",
                    }
                )

    if getattr(client, "health_awaiting_confirmation_count", 0):
        from django.utils.translation import gettext
        awaiting_docs = list(client.documents.filter(awaiting_confirmation=True, archived_at__isnull=True))
        actions = []
        for doc in awaiting_docs:
            doc_name = client.get_document_name_by_code(doc.document_type)
            actions.append({
                "label": f"{gettext('Проверить')} {doc_name}",
                "is_ocr_review": True,
                "doc_id": doc.id,
                "doc_type": doc.document_type,
            })

        if awaiting_docs:
            doc_name = client.get_document_name_by_code(awaiting_docs[0].document_type)
            action_label = _("Проверить документ: %s") % doc_name
        else:
            action_label = str(_("Проверить OCR"))

        alerts.append(
            {
                "level": "warning",
                "title": _("Есть OCR-данные без подтверждения"),
                "message": _("Документов с распознанными данными, ожидающими подтверждения: %(count)s.")
                % {"count": client.health_awaiting_confirmation_count},
                "action_label": action_label,
                "action_url": "#documentAccordion",
                "actions": actions,
            }
        )

    if getattr(client, "health_expired_documents_count", 0):
        expired_docs = list(client.documents.filter(expiry_date__lt=today, archived_at__isnull=True))
        if expired_docs:
            doc_name = client.get_document_name_by_code(expired_docs[0].document_type)
            action_label = _("Запросить документ: %s") % doc_name
        else:
            action_label = str(_("Открыть чеклист"))
        alerts.append(
            {
                "level": "danger",
                "title": _("Просроченные документы"),
                "message": _("Просроченных документов: %(count)s.") % {"count": client.health_expired_documents_count},
                "action_label": action_label,
                "action_url": "#documentAccordion",
            }
        )

    if getattr(client, "health_expiring_documents_count", 0):
        expiring_docs = list(client.documents.filter(expiry_date__gte=today, expiry_date__lte=today + timedelta(days=7), archived_at__isnull=True))
        if expiring_docs:
            doc_name = client.get_document_name_by_code(expiring_docs[0].document_type)
            action_label = _("Запросить документ: %s") % doc_name
        else:
            action_label = str(_("Открыть чеклист"))
        alerts.append(
            {
                "level": "warning",
                "title": _("Истекающие документы"),
                "message": _("Документов истекает в течение 7 дней: %(count)s.")
                % {"count": client.health_expiring_documents_count},
                "action_label": action_label,
                "action_url": "#documentAccordion",
            }
        )

    # Rejected documents check
    rejected_docs = list(client.documents.filter(rejection_reason__isnull=False, archived_at__isnull=True).exclude(rejection_reason=""))
    if rejected_docs:
        doc_name = client.get_document_name_by_code(rejected_docs[0].document_type)
        action_label = _("Запросить документ: %s") % doc_name
        alerts.append(
            {
                "level": "danger",
                "title": _("Отклонённые документы"),
                "message": _("Отклонённых документов: %(count)s.") % {"count": len(rejected_docs)},
                "action_label": action_label,
                "action_url": "#documentAccordion",
            }
        )

    if getattr(client, "health_wezwanie_count", 0) > 0:
        from django.utils.translation import gettext
        wezwanie_types = {DocumentType.WEZWANIE.value, DocumentType.WEZWANIE}
        wezwanie_docs = list(client.documents.filter(document_type__in=wezwanie_types, archived_at__isnull=True).select_related("case").order_by("-uploaded_at"))

        def _case_unnumbered(case_obj: Any) -> bool:
            # No case on the document → fall back to the client-level number.
            if case_obj is None:
                return not effective_case_number
            return not str(getattr(case_obj, "authority_case_number", "") or "").strip()

        # Only a wezwanie whose OWN case still lacks an authority number is a
        # problem; once the number is entered on that case the alert clears,
        # for single- and multi-case clients alike.
        unnumbered_docs = [
            doc for doc in wezwanie_docs
            if _case_unnumbered(doc.case if doc.case_id else None)
        ]
        if unnumbered_docs:
            actions = []
            for doc in unnumbered_docs:
                doc_label = gettext("wezwanie")
                if doc.awaiting_confirmation:
                    actions.append({
                        "label": f"{gettext('Проверить OCR')} ({doc_label})",
                        "is_ocr_review": True,
                        "doc_id": doc.id,
                        "doc_type": doc.document_type,
                    })
                else:
                    actions.append({
                        "label": f"{gettext('Открыть')} {doc_label}",
                        "url": reverse("clients:document_preview", kwargs={"doc_id": doc.id}),
                        "target": "_blank",
                    })
            # Direct "заполните case number вручную" path, tied to each
            # still-unnumbered case (works for multi-case clients too).
            fill_cases: list[Any] = []
            seen_case_ids: set[int] = set()
            for doc in unnumbered_docs:
                case_obj = doc.case if doc.case_id else None
                if case_obj is not None and case_obj.pk not in seen_case_ids:
                    seen_case_ids.add(case_obj.pk)
                    fill_cases.append(case_obj)
            if not fill_cases and active_case is not None and _case_unnumbered(active_case):
                fill_cases.append(active_case)
            for case_obj in fill_cases:
                label = gettext("Заполнить номер дела")
                if len(fill_cases) > 1:
                    label = f"{label}: {case_obj.display_number}"
                actions.append({
                    "label": label,
                    "url": reverse("clients:case_edit", kwargs={"pk": case_obj.pk}),
                })
            alerts.append(
                {
                    "level": "warning",
                    "title": _("Есть wezwanie без номера дела"),
                    "message": _("Проверьте распознавание или заполните case number вручную."),
                    "action_label": _("Запросить номер дела у клиента"),
                    "action_url": "#history",
                    "actions": actions,
                }
            )

    # Case-safe and non-cached: a multi-case client yields None here rather
    # than an arbitrary record from another case (spec §8). A fresh lookup
    # (vs. the cached_property) reflects in-request MOS updates.
    _mos_records = list(client.mos_applications.all()[:2])
    mos_application_data = _mos_records[0] if len(_mos_records) == 1 else None
    new_card_case_number = ""
    if mos_application_data is not None:
        new_card_case_number = str(mos_application_data.new_residence_card_case_number or "").strip()
    if (
        mos_application_data is not None
        and mos_application_data.new_residence_card_application_status == "yes"
        and not effective_case_number
    ):
        if new_card_case_number:
            new_card_message = _(
                "Клиент указал номер дела в блоке новой подачи, но основной номер дела в карточке пуст. "
                "Перенесите номер или проверьте присоединение к делу."
            )
        else:
            new_card_message = _(
                "Клиент сообщил о новой подаче на карту пребывания, но номер дела ещё не заполнен. "
                "Если клиент уже был на отпечатках, проверьте присоединение к делу."
            )
        new_card_actions = []
        if active_case is not None:
            from django.utils.translation import gettext
            new_card_actions.append({
                "label": gettext("Заполнить номер дела"),
                "url": reverse("clients:case_edit", kwargs={"pk": active_case.pk}),
            })
        alerts.append(
            {
                "level": "warning",
                "title": _("Новая подача требует проверки дела"),
                "message": new_card_message,
                "action_label": _("Запросить номер дела у клиента"),
                "action_url": "#history",
                "actions": new_card_actions,
            }
        )

    if effective_fingerprints_date and not getattr(client, "health_appointment_email_sent_count", 0):
        alerts.append(
            {
                "level": "warning",
                "title": _("Не отправлено письмо по отпечаткам"),
                "message": _("Дата fingerprints есть, но в истории нет appointment notification."),
                "action_label": _("Отправить письмо клиенту"),
                "action_url": "#history",
            }
        )

    if getattr(client, "health_overdue_payments_count", 0):
        alerts.append(
            {
                "level": "warning",
                "title": _("Просроченные оплаты"),
                "message": _("Оплат с due date сегодня или раньше: %(count)s.")
                % {"count": client.health_overdue_payments_count},
                "action_label": _("Открыть финансы"),
                "action_url": "#payment-list-container",
            }
        )

    failed_emails_count = client.email_logs.filter(delivery_status="failed").count()
    if failed_emails_count:
        alerts.append(
            {
                "level": "danger",
                "title": _("Ошибка отправки писем клиенту"),
                "message": _("Не удалось отправить писем клиенту: %(count)s. Проверьте правильность email-адреса.")
                % {"count": failed_emails_count},
                "action_label": _("Открыть историю писем"),
                "action_url": "#history",
            }
        )

    if document_status_list is None:
        document_status_list = client.get_document_checklist()
    missing_documents_count = sum(1 for item in document_status_list if not item["is_complete"])
    if missing_documents_count:
        first_missing = next((item for item in document_status_list if not item["is_complete"]), None)
        if first_missing:
            action_label = _("Запросить документ: %s") % first_missing["name"]
        else:
            action_label = str(_("Открыть чеклист"))
        alerts.append(
            {
                "level": "info",
                "title": _("Не все документы собраны"),
                "message": _("Не хватает обязательных документов: %(count)s.")
                % {"count": missing_documents_count},
                "count": missing_documents_count,
                "action_label": action_label,
                "action_url": "#documentAccordion",
            }
        )

    from clients.services.cases import resolve_single_active_case

    zus_case = resolve_single_active_case(client)
    if (
        zus_case is not None
        and zus_case.workflow_stage == "waiting_decision"
        and zus_case.fingerprints_date
        and zus_case.fingerprints_date <= today
        and not zus_case.decision_date
    ):
        from clients.services.zus import format_zus_months, missing_zus_months

        missing_zus = missing_zus_months(zus_case, today=today)
        if missing_zus:
            month_name = format_zus_months([missing_zus[0]])
            action_label = _("Запросить ZUS RCA за %s") % month_name
            alerts.append(
                {
                    "level": "warning",
                    "title": _("ZUS RCA — пропущены месяцы"),
                    "message": _("Нет ZUS RCA за месяцы: %(months)s.")
                    % {"months": format_zus_months(missing_zus)},
                    "count": len(missing_zus),
                    "action_label": action_label,
                    "action_url": "#documentAccordion",
                }
            )

    family_group = client._get_family_group_for_income_check()
    if family_group is not None:
        from clients.services.family import calculate_family_income

        family_income = calculate_family_income(family_group)
        for risk in family_income.risks:
            alerts.append(
                {
                    "level": "warning",
                    "title": risk["title"],
                    "message": risk["message"],
                    "action_label": _("Открыть семейную группу"),
                    "action_url": reverse("clients:family_dashboard", kwargs={"pk": client.pk}),
                }
            )

    if getattr(client, "health_overdue_tasks_count", 0):
        first_overdue = client.staff_tasks.filter(status__in=["open", "in_progress"], due_date__lt=today).first()
        if first_overdue:
            action_label = _("Выполнить задачу: %s") % first_overdue.title
        else:
            action_label = str(_("Выполнить просроченные задачи"))
        alerts.append(
            {
                "level": "danger",
                "title": _("Есть просроченные задачи"),
                "message": _("Просроченных задач: %(count)s.") % {"count": client.health_overdue_tasks_count},
                "action_label": action_label,
                "action_url": "#overview",
            }
        )

    # RODO art. 17/12(3): a pending erasure request has a one-month statutory
    # response clock. Surface it to staff before the deadline is breached.
    erasure_state = _erasure_deadline_state(client, today)
    if erasure_state is not None:
        severity, days_left = erasure_state
        if severity == "danger":
            alerts.append(
                {
                    "level": "danger",
                    "title": _("RODO: срок ответа на запрос об удалении истёк"),
                    "message": _("Запрос на удаление данных (RODO art. 17) просрочен на %(days)s дн. "
                                 "Требуется немедленно обработать (анонимизация/удаление).")
                    % {"days": abs(days_left)},
                    "action_label": _("Обработать запрос на удаление"),
                    "action_url": "#overview",
                }
            )
        elif severity == "warning":
            alerts.append(
                {
                    "level": "warning",
                    "title": _("RODO: приближается срок ответа на запрос об удалении"),
                    "message": _("До законного срока ответа на запрос об удалении осталось %(days)s дн.")
                    % {"days": days_left},
                    "action_label": _("Обработать запрос на удаление"),
                    "action_url": "#overview",
                }
            )

    # Check inactivity 30+ days
    if client.get_effective_workflow_stage() not in ["closed", "decision_received"]:
        latest_act = client.activities.exclude(event_type="client_viewed").order_by("-created_at").first()
        last_action_date = latest_act.created_at.date() if latest_act else client.created_at.date()
        if last_action_date < today - timedelta(days=30):
            alerts.append(
                {
                    "level": "warning",
                    "title": _("Бездействие по делу более 30 дней"),
                    "message": _("Последнее значимое действие было %(days)s дней назад (%(date)s).") % {
                        "days": (today - last_action_date).days,
                        "date": last_action_date.strftime("%d.%m.%Y"),
                    },
                    "action_label": _("Связаться с клиентом"),
                    "action_url": "#history",
                }
            )

    return alerts

def build_automatic_checks(client: "Client", document_status_list: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    today = timezone.localdate()
    # Read the case number and fingerprints date from the single active case
    # (spec §4) rather than the legacy client mirror.
    from clients.services.cases import resolve_single_active_case

    active_case = resolve_single_active_case(client)
    effective_case_number = (
        (active_case.authority_case_number if active_case is not None else "") or ""
    )
    effective_fingerprints_date = (
        active_case.fingerprints_date if active_case is not None else None
    )
    if not hasattr(client, "health_awaiting_confirmation_count"):
        stats = (
            client.__class__.objects.filter(pk=client.pk)
            .with_health_stats(today=today)
            .values(
                "health_awaiting_confirmation_count",
                "health_expired_documents_count",
                "health_expiring_documents_count",
                "health_wezwanie_count",
                "health_appointment_email_sent_count",
                "health_overdue_payments_count",
                "health_overdue_tasks_count",
            )
            .get()
        )
        for key, value in stats.items():
            setattr(client, key, value)

    checks = []
    edit_url = reverse("clients:client_edit", kwargs={"pk": client.pk})

    # 1. Stay Validity
    legal_stay_date = client.legal_basis_end_date or client._get_mos_legal_stay_until()

    if client.has_submitted_case:
        # Submitted to the urząd: the stamp legalises the stay, so the old
        # card expiry is no longer a risk.
        checks.append({
            "label": _("Легальность пребывания"),
            "status": "success",
            "message": _("Дело подано в ужонд — пребывание легально по штампу"),
            "tooltip": _("Дело подано в воеводский ужонд; пребывание легализовано штампом на время рассмотрения."),
        })
    elif not legal_stay_date:
        checks.append({
            "label": _("Легальность пребывания"),
            "status": "warning",
            "message": _("Дата не указана"),
            "tooltip": _("Проверка срока законного нахождения в стране. Дата окончания пребывания не задана."),
            "action_url": edit_url,
        })
    elif legal_stay_date < today:
        checks.append({
            "label": _("Легальность пребывания"),
            "status": "danger",
            "message": _("Истекло %s") % legal_stay_date.strftime("%d.%m.%Y"),
            "tooltip": _("Основание пребывания клиента истекло. Требуется срочное продление или связь с клиентом."),
            "action_url": edit_url,
        })
    elif legal_stay_date <= today + timedelta(days=30):
        checks.append({
            "label": _("Легальность пребывания"),
            "status": "warning",
            "message": _("Истекает %s") % legal_stay_date.strftime("%d.%m.%Y"),
            "tooltip": _("Основание пребывания истекает менее чем через 30 дней."),
            "action_url": edit_url,
        })
    else:
        checks.append({
            "label": _("Легальность пребывания"),
            "status": "success",
            "message": _("Действительно до %s") % legal_stay_date.strftime("%d.%m.%Y"),
            "tooltip": _("Основание пребывания действительно (более 30 дней)."),
            "action_url": edit_url,
        })

    # 2. Documents completion
    if document_status_list is None:
        document_status_list = client.get_document_checklist()
    missing_count = sum(1 for item in document_status_list if not item["is_complete"])
    if missing_count:
        checks.append({
            "label": _("Комплект документов"),
            "status": "warning",
            "message": _("Не хватает: %s") % missing_count,
            "tooltip": _("В чеклисте присутствуют незагруженные обязательные документы для выбранного основания."),
            "action_url": "#documentAccordion",
        })
    else:
        checks.append({
            "label": _("Комплект документов"),
            "status": "success",
            "message": _("Собрано"),
            "tooltip": _("Все обязательные документы по чеклисту успешно загружены."),
            "action_url": "#documentAccordion",
        })

    # 3. Expired documents
    if getattr(client, "health_expired_documents_count", 0):
        checks.append({
            "label": _("Срок действия документов"),
            "status": "danger",
            "message": _("Просрочено: %s") % client.health_expired_documents_count,
            "tooltip": _("Среди загруженных документов есть просроченные файлы."),
            "action_url": "#documentAccordion",
        })
    elif getattr(client, "health_expiring_documents_count", 0):
        checks.append({
            "label": _("Срок действия документов"),
            "status": "warning",
            "message": _("Истекает: %s") % client.health_expiring_documents_count,
            "tooltip": _("Среди загруженных документов есть те, которые истекают в течение 7 дней."),
            "action_url": "#documentAccordion",
        })
    else:
        checks.append({
            "label": _("Срок действия документов"),
            "status": "success",
            "message": _("OK"),
            "tooltip": _("Все загруженные документы действительны."),
            "action_url": "#documentAccordion",
        })

    # 4. OCR confirmation
    if getattr(client, "health_awaiting_confirmation_count", 0):
        checks.append({
            "label": _("Подтверждение OCR"),
            "status": "warning",
            "message": _("Ожидает: %s") % client.health_awaiting_confirmation_count,
            "tooltip": _("Есть документы с автоматическим распознаванием текста, которые сотрудник ещё не подтвердил."),
            "action_url": "#documentAccordion",
        })
    else:
        checks.append({
            "label": _("Подтверждение OCR"),
            "status": "success",
            "message": _("Подтверждено"),
            "tooltip": _("Нет документов, ожидающих проверки распознанных данных."),
            "action_url": "#documentAccordion",
        })

    # 5. Case Number
    if getattr(client, "health_wezwanie_count", 0) > 0 and not effective_case_number:
        checks.append({
            "label": _("Номер дела"),
            "status": "warning",
            "message": _("Не указан"),
            "tooltip": _("Загружен документ Wezwanie, но номер дела (Case number) в системе не заполнен."),
            "action_url": edit_url,
        })
    else:
        checks.append({
            "label": _("Номер дела"),
            "status": "success",
            "message": effective_case_number or _("OK (нет wezwanie)"),
            "tooltip": _("Номер дела заполнен или нет документов Wezwanie, требующих его наличия."),
            "action_url": edit_url,
        })

    # 6. Payments
    if getattr(client, "health_overdue_payments_count", 0):
        checks.append({
            "label": _("Оплата по договору"),
            "status": "warning",
            "message": _("Просрочено платежей: %s") % client.health_overdue_payments_count,
            "tooltip": _("Есть выставленные платежи с наступившим сроком оплаты, которые не оплачены."),
            "action_url": "#payment-list-container",
        })
    else:
        checks.append({
            "label": _("Оплата по договору"),
            "status": "success",
            "message": _("Оплачено"),
            "tooltip": _("Нет просроченных платежей по договору."),
            "action_url": "#payment-list-container",
        })

    # 7. Fingerprints letter
    if effective_fingerprints_date and not getattr(client, "health_appointment_email_sent_count", 0):
        checks.append({
            "label": _("Письмо об отпечатках"),
            "status": "warning",
            "message": _("Не отправлено"),
            "tooltip": _("Указана дата сдачи отпечатков, но письмо-напоминание клиенту ещё не было отправлено."),
            "action_url": edit_url,
        })
    else:
        checks.append({
            "label": _("Письмо об отпечатках"),
            "status": "success",
            "message": _("OK"),
            "tooltip": _("Письмо об отпечатках отправлено, либо дата отпечатков не назначена."),
            "action_url": edit_url,
        })

    # 8. ZUS RCA months (case-first; ambiguous multi-case clients skipped)
    from clients.services.cases import resolve_single_active_case

    zus_case = resolve_single_active_case(client)
    if (
        zus_case is not None
        and zus_case.workflow_stage == "waiting_decision"
        and zus_case.fingerprints_date
        and zus_case.fingerprints_date <= today
        and not zus_case.decision_date
    ):
        from clients.services.zus import missing_zus_months
        missing_zus = missing_zus_months(zus_case, today=today)
        if missing_zus:
            checks.append({
                "label": _("Отчёты ZUS RCA"),
                "status": "warning",
                "message": _("Пропущено месяцев: %s") % len(missing_zus),
                "tooltip": _("В системе отсутствуют отчёты ZUS RCA за некоторые месяцы после сдачи отпечатков."),
                "action_url": "#documentAccordion",
            })
        else:
            checks.append({
                "label": _("Отчёты ZUS RCA"),
                "status": "success",
                "message": _("OK"),
                "tooltip": _("Все необходимые ежемесячные отчёты ZUS RCA загружены."),
                "action_url": "#documentAccordion",
            })
    else:
        checks.append({
            "label": _("Отчёты ZUS RCA"),
            "status": "success",
            "message": _("Не требуется"),
            "tooltip": _("Проверка ZUS RCA активна только на этапе ожидания решения после отпечатков."),
            "action_url": "#documentAccordion",
        })

    # 9. Staff Tasks
    if getattr(client, "health_overdue_tasks_count", 0):
        checks.append({
            "label": _("Задачи по делу"),
            "status": "danger",
            "message": _("Просрочено: %s") % client.health_overdue_tasks_count,
            "tooltip": _("Среди задач по этому клиенту есть просроченные сотрудником задачи."),
            "action_url": "#overview",
        })
    else:
        checks.append({
            "label": _("Задачи по делу"),
            "status": "success",
            "message": _("OK"),
            "tooltip": _("Нет просроченных задач по делу клиента."),
            "action_url": "#overview",
        })

    # 10. Family Income
    family_group = client._get_family_group_for_income_check()

    if family_group is not None:
        from clients.services.family import calculate_family_income
        family_income = calculate_family_income(family_group)
        family_url = reverse("clients:family_dashboard", kwargs={"pk": client.pk})
        if family_income.risks:
            checks.append({
                "label": _("Доходы семьи"),
                "status": "warning",
                "message": _("Недостаточно"),
                "tooltip": _("Доходы семьи не соответствуют требованиям законодательства о прожиточном минимуме."),
                "action_url": family_url,
            })
        else:
            checks.append({
                "label": _("Доходы семьи"),
                "status": "success",
                "message": _("Достаточно"),
                "tooltip": _("Расчёт доходов подтверждает финансовую достаточность для семьи."),
                "action_url": family_url,
            })
    else:
        checks.append({
            "label": _("Доходы семьи"),
            "status": "success",
            "message": _("Не применимо"),
            "tooltip": _("Проверка доходов активна только для членов семейных групп."),
        })

    # 11. RODO erasure request (art. 17). Only shown while a request is open, so
    # the dashboard is not cluttered for the common case with no pending request.
    erasure_state = _erasure_deadline_state(client, today)
    if erasure_state is not None:
        severity, days_left = erasure_state
        if severity == "danger":
            checks.append({
                "label": _("RODO: запрос на удаление"),
                "status": "danger",
                "message": _("Просрочен на %s дн.") % abs(days_left),
                "tooltip": _("Истёк законный срок (1 месяц) ответа на запрос об удалении данных (RODO art. 12(3))."),
                "action_url": "#overview",
            })
        elif severity == "warning":
            checks.append({
                "label": _("RODO: запрос на удаление"),
                "status": "warning",
                "message": _("Осталось %s дн.") % days_left,
                "tooltip": _("Приближается законный срок ответа на запрос об удалении данных (RODO art. 12(3))."),
                "action_url": "#overview",
            })
        else:
            checks.append({
                "label": _("RODO: запрос на удаление"),
                "status": "success",
                "message": _("В обработке (%s дн.)") % days_left,
                "tooltip": _("Открыт запрос на удаление данных; срок ответа соблюдается."),
                "action_url": "#overview",
            })

    return checks
