import hashlib
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from fernet_fields import EncryptedTextField

from clients.constants import DocumentType
from legalize_site.soft_delete import SoftDeleteModel


class Client(SoftDeleteModel):
    _application_purpose_display_cache: dict[str, dict[str, str]] = {}

    APPLICATION_PURPOSE_CHOICES = [
        ("study", _("Учёба")),
        ("work", _("Работа")),
        ("family", _("Воссоединение с семьёй")),
    ]
    FAMILY_MEMBER_REQUIREMENT_PURPOSES = {"family_spouse", "family_child"}
    DOCUMENT_REQUIREMENT_PURPOSE_CHOICES = [
        ("study", _("Учёба")),
        ("work", _("Работа")),
        ("family_spouse", _("Супруг/супруга")),
        ("family_child", _("Ребёнок")),
    ]
    FAMILY_ROLE_CHOICES = [
        ("", _("Не указано")),
        ("sponsor", _("Спонсор")),
        ("family_spouse", _("Супруг/супруга")),
        ("family_child", _("Ребёнок")),
    ]
    LANGUAGE_CHOICES = getattr(
        settings,
        "LANGUAGES",
        [
            ("pl", _("Польский")),
            ("en", _("Английский")),
            ("ru", _("Русский")),
        ],
    )
    STATUS_CHOICES = [
        ("new", _("Новый")),
        ("pending", _("В ожидании")),
        ("approved", _("Одобрен")),
        ("rejected", _("Отклонён")),
    ]
    WORKFLOW_STAGE_CHOICES = [
        ("new_client", _("Новый клиент")),
        ("document_collection", _("Сбор документов")),
        ("application_submitted", _("Подача")),
        ("fingerprints", _("Отпечатки")),
        ("waiting_decision", _("Ожидание решения")),
        ("decision_received", _("Децизия")),
        ("closed", _("Закрыто")),
    ]

    first_name = models.CharField(max_length=100, verbose_name=_("Имя"))
    last_name = models.CharField(max_length=100, verbose_name=_("Фамилия"))
    citizenship = models.CharField(max_length=100, verbose_name=_("Гражданство"))
    birth_date = models.DateField(null=True, blank=True, verbose_name=_("Дата рождения"))
    phone = models.CharField(max_length=20, verbose_name=_("Телефон"))
    email = models.EmailField(verbose_name="Email")
    passport_num = EncryptedTextField(null=True, blank=True, verbose_name=_("Номер паспорта"))
    case_number = EncryptedTextField(blank=True, null=True, verbose_name=_("Номер дела"))
    case_number_hash = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    application_purpose = models.CharField(
        max_length=64,
        default="study",
        verbose_name=_("Цель подачи"),
    )
    basis_of_stay = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("Основание пребывания (виза, TRC и т.д.)"),
    )
    language = models.CharField(
        max_length=5,
        choices=LANGUAGE_CHOICES,
        default="pl",
        verbose_name=_("Язык документов"),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new", verbose_name=_("Статус"))
    workflow_stage = models.CharField(
        max_length=32,
        choices=WORKFLOW_STAGE_CHOICES,
        default="new_client",
        verbose_name=_("Этап workflow"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))
    legal_basis_end_date = models.DateField(null=True, blank=True, verbose_name=_("Дата окончания основания"))
    submission_date = models.DateField(null=True, blank=True, verbose_name=_("Дата подачи (Złożone)"))
    employer_phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name=_("Телефон работодателя"),
    )
    fingerprints_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Дата сдачи отпечатков"),
    )
    fingerprints_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name=_("Время сдачи отпечатков"),
    )
    fingerprints_location = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("Место сдачи отпечатков"),
    )
    fingerprints_ticket = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("Номер билета (Bilet)"),
    )
    fingerprints_list = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("Название списка (Lista)"),
    )
    fingerprints_info = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Дополнительная информация (кабинет, окно и т.д.)"),
    )
    decision_date = models.DateField(

        null=True,
        blank=True,
        verbose_name=_("Дата официальной децизии"),
    )
    notes = models.TextField(blank=True, null=True, verbose_name=_("Uwagi / Заметки"))
    has_checklist_access = models.BooleanField(default=False, verbose_name=_("Доступ к чеклисту предоставлен"))
    family_role = models.CharField(
        max_length=32,
        choices=FAMILY_ROLE_CHOICES,
        blank=True,
        default="",
        verbose_name=_("Роль в семье"),
    )
    sponsor_client = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sponsored_family_members",
        verbose_name=_("Спонсор"),
    )

    company = models.ForeignKey(
        "Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clients",
        verbose_name=_("Компания / Работодатель"),
    )
    assigned_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_clients",
        verbose_name=_("Assigned staff"),
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="client_profile",
        null=True,
        blank=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["assigned_staff", "status"], name="client_staff_status_idx"),
            models.Index(fields=["workflow_stage", "status"], name="client_workflow_status_idx"),
            models.Index(fields=["created_at"], name="client_created_at_idx"),
            models.Index(fields=["sponsor_client", "family_role"], name="client_family_role_idx"),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def on_archive(self):
        if not self.user_id:
            return

        from django.contrib.auth import get_user_model

        user = get_user_model().objects.filter(pk=self.user_id).first()
        if user and not user.is_staff and user.is_active:
            user.is_active = False
            user.save(update_fields=["is_active"])

    @staticmethod
    def normalize_case_number(case_number: str) -> str:
        return case_number.strip().upper().replace(" ", "")

    @classmethod
    def hash_case_number(cls, case_number: str) -> str:
        normalized = cls.normalize_case_number(case_number)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def save(self, *args, **kwargs):
        if self.case_number:
            self.case_number_hash = self.hash_case_number(self.case_number)
        else:
            self.case_number_hash = None

        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "case_number" in update_fields:
            update_fields = set(update_fields)
            update_fields.add("case_number_hash")
            kwargs["update_fields"] = list(update_fields)

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("clients:client_detail", kwargs={"pk": self.id})

    def get_application_purpose_display(self):
        from submissions.models import Submission

        fallback = dict(self.APPLICATION_PURPOSE_CHOICES).get(
            self.application_purpose,
            self.application_purpose or "",
        )
        if self.application_purpose:
            current_language = translation.get_language() or self.language or "pl"
            language_code = current_language.split("-")[0].lower()
            display_map = self._application_purpose_display_cache.get(language_code)
            if display_map is None:
                display_map = {}
                for submission in Submission.objects.all().only(
                    "slug",
                    "name",
                    "name_pl",
                    "name_en",
                    "name_ru",
                ):
                    localized = getattr(submission, f"name_{language_code}", None)
                    display_map[submission.slug] = localized.strip() if localized and localized.strip() else submission.name
                self._application_purpose_display_cache[language_code] = display_map
            if self.application_purpose in display_map:
                return display_map[self.application_purpose]

        return fallback

    def get_document_requirement_purpose(self) -> str:
        if self.application_purpose == "family":
            if self.family_role in self.FAMILY_MEMBER_REQUIREMENT_PURPOSES:
                return self.family_role
            if self.family_role == "sponsor":
                return "work"
        return self.application_purpose

    def get_submitted_document_summary(self):
        from clients.services.wniosek import build_submitted_document_summary

        return build_submitted_document_summary(self)

    def get_submitted_document_codes(self) -> set[str]:
        summary = self.get_submitted_document_summary()
        return set(summary.get("codes", {}).keys())

    def get_document_checklist(self, check_file_existence: bool = False):
        from .document import DocumentRequirement, resolve_document_label
        from clients.services.document_helpers import document_file_exists

        current_language = translation.get_language() or self.language
        purpose = self.get_document_requirement_purpose()
        required_docs = DocumentRequirement.required_for(purpose, current_language)
        prefetched_documents = getattr(self, "_prefetched_objects_cache", {}).get("documents")
        if prefetched_documents is None:
            uploaded_docs = self.documents.all().annotate(
                preloaded_version_count=models.Count("versions")
            ).order_by("-uploaded_at")
        else:
            uploaded_docs = sorted(
                prefetched_documents,
                key=lambda document: document.uploaded_at,
                reverse=True,
            )

        reqs = DocumentRequirement.objects.filter(application_purpose=purpose)
        req_map = {r.document_type: r for r in reqs}

        docs_map = {}
        for doc in uploaded_docs:
            doc._preloaded_version_count = getattr(doc, "preloaded_version_count", 0)
            doc._preloaded_requirement = req_map.get(doc.document_type)
            if check_file_existence:
                doc.file_exists = document_file_exists(doc)
            docs_map.setdefault(doc.document_type, []).append(doc)

        submitted_summary = self.get_submitted_document_summary()
        submitted_by_code = submitted_summary.get("codes", {})
        custom_submissions = submitted_summary.get("custom", [])

        status_list = []
        seen_codes = set()
        for code, name in required_docs:
            documents = docs_map.get(code, [])
            submitted_records = submitted_by_code.get(code, [])
            status_list.append(
                {
                    "code": code,
                    "name": str(name),
                    "is_uploaded": bool(documents),
                    "is_submitted": bool(submitted_records),
                    "is_complete": bool(documents) or bool(submitted_records),
                    "documents": documents,
                    "submitted_records": submitted_records,
                    "is_custom_submission": False,
                }
            )
            seen_codes.add(code)

        for code, submitted_records in submitted_by_code.items():
            if code in seen_codes:
                continue
            documents = docs_map.get(code, [])
            status_list.append(
                {
                    "code": code,
                    "name": str(resolve_document_label(code, language=current_language)),
                    "is_uploaded": bool(documents),
                    "is_submitted": bool(submitted_records),
                    "is_complete": bool(documents) or bool(submitted_records),
                    "documents": documents,
                    "submitted_records": submitted_records,
                    "is_custom_submission": False,
                }
            )
            seen_codes.add(code)

        for code, documents in docs_map.items():
            if code in seen_codes:
                continue
            status_list.append(
                {
                    "code": code,
                    "name": str(resolve_document_label(code, language=current_language)),
                    "is_uploaded": bool(documents),
                    "is_submitted": False,
                    "is_complete": bool(documents),
                    "documents": documents,
                    "submitted_records": [],
                    "is_custom_submission": False,
                }
            )
            seen_codes.add(code)

        for index, custom_item in enumerate(custom_submissions):
            status_list.append(
                {
                    "code": f"submitted-custom-{index}",
                    "name": str(custom_item["name"]),
                    "is_uploaded": False,
                    "is_submitted": True,
                    "is_complete": True,
                    "documents": [],
                    "submitted_records": custom_item.get("records", []),
                    "is_custom_submission": True,
                }
            )
        return status_list

    def get_document_name_by_code(self, doc_code):
        from .document import DocumentRequirement, get_available_document_types, resolve_document_label

        current_language = translation.get_language() or self.language
        purpose = self.get_document_requirement_purpose()
        catalog = DocumentRequirement.catalog_for(
            purpose,
            current_language,
            include_optional=True,
            include_fallback=True,
        )
        for item in catalog:
            if item["code"] == doc_code:
                return item["label"]
        if doc_code in get_available_document_types(purpose):
            return resolve_document_label(doc_code, language=current_language)
        return doc_code.replace("_", " ").capitalize()

    def get_health_alerts(self, document_status_list=None):
        alerts = []
        today = timezone.localdate()
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        prefetched_documents = prefetched.get("documents")
        prefetched_payments = prefetched.get("payments")
        prefetched_email_logs = prefetched.get("email_logs")
        prefetched_staff_tasks = prefetched.get("staff_tasks")

        if self.legal_basis_end_date:
            if self.legal_basis_end_date < today:
                alerts.append(
                    {
                        "level": "danger",
                        "title": _("Основание пребывания уже истекло"),
                        "message": _("Проверьте основание пребывания и срочно свяжитесь с клиентом."),
                    }
                )
            elif self.legal_basis_end_date <= today + timedelta(days=30):
                alerts.append(
                    {
                        "level": "warning",
                        "title": _("Основание пребывания скоро истекает"),
                        "message": _("До окончания основания пребывания осталось меньше 30 дней."),
                    }
                )

        if prefetched_documents is None:
            awaiting_confirmation_count = self.documents.filter(awaiting_confirmation=True).count()
        else:
            awaiting_confirmation_count = sum(1 for document in prefetched_documents if document.awaiting_confirmation)
        if awaiting_confirmation_count:
            alerts.append(
                {
                    "level": "warning",
                    "title": _("Есть OCR-данные без подтверждения"),
                    "message": _("Документов с распознанными данными, ожидающими подтверждения: %(count)s.")
                    % {"count": awaiting_confirmation_count},
                    "action_label": _("Проверить OCR"),
                    "action_url": "#documentAccordion",
                }
            )

        if prefetched_documents is None:
            expired_documents_count = self.documents.filter(expiry_date__isnull=False, expiry_date__lt=today).count()
        else:
            expired_documents_count = sum(
                1
                for document in prefetched_documents
                if document.expiry_date and document.expiry_date < today
            )
        if expired_documents_count:
            alerts.append(
                {
                    "level": "danger",
                    "title": _("Просроченные документы"),
                    "message": _("Просроченных документов: %(count)s.") % {"count": expired_documents_count},
                    "action_label": _("Открыть чеклист"),
                    "action_url": "#documentAccordion",
                }
            )

        expiring_cutoff = today + timedelta(days=7)
        if prefetched_documents is None:
            expiring_documents_count = self.documents.filter(
                expiry_date__isnull=False,
                expiry_date__gte=today,
                expiry_date__lte=expiring_cutoff,
            ).count()
        else:
            expiring_documents_count = sum(
                1
                for document in prefetched_documents
                if document.expiry_date and today <= document.expiry_date <= expiring_cutoff
            )
        if expiring_documents_count:
            alerts.append(
                {
                    "level": "warning",
                    "title": _("Истекающие документы"),
                    "message": _("Документов истекает в течение 7 дней: %(count)s.")
                    % {"count": expiring_documents_count},
                    "action_label": _("Открыть чеклист"),
                    "action_url": "#documentAccordion",
                }
            )

        wezwanie_types = {DocumentType.WEZWANIE, DocumentType.WEZWANIE.value}
        if prefetched_documents is None:
            wezwanie_exists = self.documents.filter(document_type__in=wezwanie_types).exists()
        else:
            wezwanie_exists = any(document.document_type in wezwanie_types for document in prefetched_documents)
        if wezwanie_exists and not self.case_number:
            alerts.append(
                {
                    "level": "warning",
                    "title": _("Есть wezwanie без номера дела"),
                    "message": _("Проверьте распознавание или заполните case number вручную."),
                }
            )

        if prefetched_email_logs is None:
            appointment_email_sent = self.email_logs.filter(template_type="appointment_notification").exists()
        else:
            appointment_email_sent = any(
                email_log.template_type == "appointment_notification"
                for email_log in prefetched_email_logs
            )
        if self.fingerprints_date and not appointment_email_sent:
            alerts.append(
                {
                    "level": "warning",
                    "title": _("Не отправлено письмо по отпечаткам"),
                    "message": _("Дата fingerprints есть, но в истории нет appointment notification."),
                }
            )

        if prefetched_payments is None:
            overdue_payments_count = self.payments.filter(
                status__in=["pending", "partial"],
                due_date__isnull=False,
                due_date__lte=today,
            ).count()
        else:
            overdue_payments_count = sum(
                1
                for payment in prefetched_payments
                if payment.status in {"pending", "partial"} and payment.due_date and payment.due_date <= today
            )
        if overdue_payments_count:
            alerts.append(
                {
                    "level": "warning",
                    "title": _("Просроченные оплаты"),
                    "message": _("Оплат с due date сегодня или раньше: %(count)s.")
                    % {"count": overdue_payments_count},
                    "action_label": _("Открыть финансы"),
                    "action_url": "#payment-list-container",
                }
            )

        if document_status_list is None:
            document_status_list = self.get_document_checklist()
        missing_documents_count = sum(1 for item in document_status_list if not item["is_complete"])
        if missing_documents_count:
            alerts.append(
                {
                    "level": "info",
                    "title": _("Не все документы собраны"),
                    "message": _("Отсутствует обязательных документов: %(count)s.")
                    % {"count": missing_documents_count},
                    "count": missing_documents_count,
                    "action_label": _("Открыть чеклист"),
                    "action_url": "#documentAccordion",
                }
            )

        if (
            self.workflow_stage == "waiting_decision"
            and self.fingerprints_date
            and self.fingerprints_date <= today
            and not self.decision_date
        ):
            from clients.services.zus import format_zus_months, missing_zus_months

            missing_zus = missing_zus_months(self, today=today)
            if missing_zus:
                alerts.append(
                    {
                        "level": "warning",
                        "title": _("ZUS RCA — пропущены месяцы"),
                        "message": _("Нет ZUS RCA за месяцы: %(months)s.")
                        % {"months": format_zus_months(missing_zus)},
                        "count": len(missing_zus),
                        "action_label": _("Открыть чеклист"),
                        "action_url": "#documentAccordion",
                    }
                )

        family_group = None
        try:
            family_group = self.family_group
        except Exception:
            family_group = None
        if family_group is None and self.sponsor_client_id:
            try:
                family_group = self.sponsor_client.family_group
            except Exception:
                family_group = None
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
                        "action_url": reverse("clients:family_dashboard", kwargs={"pk": self.pk}),
                    }
                )

        if prefetched_staff_tasks is None:
            overdue_tasks_count = self.staff_tasks.filter(
                status__in=["open", "in_progress"],
                due_date__lt=today,
            ).count()
        else:
            overdue_tasks_count = sum(
                1
                for task in prefetched_staff_tasks
                if task.status in {"open", "in_progress"} and task.due_date and task.due_date < today
            )
        if overdue_tasks_count:
            alerts.append(
                {
                    "level": "danger",
                    "title": _("Есть просроченные задачи"),
                    "message": _("Просроченных задач: %(count)s.") % {"count": overdue_tasks_count},
                }
            )

        return alerts

    def get_workflow_summary(self, document_status_list=None):
        alerts = self.get_health_alerts(document_status_list=document_status_list)
        prefetched_staff_tasks = getattr(self, "_prefetched_objects_cache", {}).get("staff_tasks")
        if prefetched_staff_tasks is None:
            open_tasks = self.staff_tasks.filter(status__in=["open", "in_progress"])
            open_tasks_count = open_tasks.count()
            overdue_tasks = open_tasks.filter(due_date__lt=timezone.localdate()).count()
        else:
            today = timezone.localdate()
            open_tasks_list = [
                task for task in prefetched_staff_tasks if task.status in {"open", "in_progress"}
            ]
            open_tasks_count = len(open_tasks_list)
            overdue_tasks = sum(1 for task in open_tasks_list if task.due_date and task.due_date < today)
        return {
            "stage_label": self.get_workflow_stage_display(),
            "alerts": alerts,
            "alerts_count": len(alerts),
            "open_tasks_count": open_tasks_count,
            "overdue_tasks_count": overdue_tasks,
        }
