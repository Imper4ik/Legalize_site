from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any, cast, Self, TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from fernet_fields import EncryptedTextField

from clients.constants import DocumentType
from legalize_site.soft_delete import SoftDeleteModel, SoftDeleteQuerySet

if TYPE_CHECKING:
    from .document import Document


class ClientQuerySet(SoftDeleteQuerySet):
    def with_health_stats(self, today: date | None = None) -> Self:
        if today is None:
            today = timezone.localdate()
        expiring_cutoff = today + timedelta(days=7)
        wezwanie_types = {DocumentType.WEZWANIE, DocumentType.WEZWANIE.value}

        return self.annotate(
            health_awaiting_confirmation_count=Count(
                "documents",
                filter=Q(documents__awaiting_confirmation=True, documents__archived_at__isnull=True),
                distinct=True,
            ),
            health_expired_documents_count=Count(
                "documents",
                filter=Q(
                    documents__expiry_date__isnull=False,
                    documents__expiry_date__lt=today,
                    documents__archived_at__isnull=True,
                ),
                distinct=True,
            ),
            health_expiring_documents_count=Count(
                "documents",
                filter=Q(
                    documents__expiry_date__isnull=False,
                    documents__expiry_date__gte=today,
                    documents__expiry_date__lte=expiring_cutoff,
                    documents__archived_at__isnull=True,
                ),
                distinct=True,
            ),
            health_wezwanie_count=Count(
                "documents",
                filter=Q(documents__document_type__in=wezwanie_types, documents__archived_at__isnull=True),
                distinct=True,
            ),
            health_appointment_email_sent_count=Count(
                "email_logs",
                filter=Q(email_logs__template_type="appointment_notification"),
                distinct=True,
            ),
            health_overdue_payments_count=Count(
                "payments",
                filter=Q(
                    payments__status__in=["pending", "partial"],
                    payments__due_date__isnull=False,
                    payments__due_date__lte=today,
                    payments__archived_at__isnull=True,
                ),
                distinct=True,
            ),
            health_overdue_tasks_count=Count(
                "staff_tasks",
                filter=Q(
                    staff_tasks__status__in=["open", "in_progress"],
                    staff_tasks__due_date__lt=today,
                ),
                distinct=True,
            ),
        )


class ClientManager(models.Manager.from_queryset(ClientQuerySet)):  # type: ignore[misc]
    def get_queryset(self) -> ClientQuerySet:
        return cast(ClientQuerySet, super().get_queryset().active())


class Client(SoftDeleteModel):
    objects = ClientManager()  # type: ignore[misc]
    all_objects = ClientQuerySet.as_manager()  # type: ignore[misc]
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
    citizenship = models.CharField(max_length=100, blank=True, verbose_name=_("Гражданство"))
    birth_date = models.DateField(null=True, blank=True, verbose_name=_("Дата рождения"))
    phone = models.CharField(max_length=20, blank=True, verbose_name=_("Телефон"))
    email = models.EmailField(blank=True, verbose_name="Email")
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

    if TYPE_CHECKING:
        health_awaiting_confirmation_count: int
        health_expired_documents_count: int
        health_expiring_documents_count: int
        health_wezwanie_count: int
        health_appointment_email_sent_count: int
        health_overdue_payments_count: int
        health_overdue_tasks_count: int
        family_group: Any

    class Meta:
        indexes = [
            models.Index(fields=["assigned_staff", "status"], name="client_staff_status_idx"),
            models.Index(fields=["workflow_stage", "status"], name="client_workflow_status_idx"),
            models.Index(fields=["created_at"], name="client_created_at_idx"),
            models.Index(fields=["sponsor_client", "family_role"], name="client_family_role_idx"),
            models.Index(fields=["email"], name="client_email_idx"),
            models.Index(fields=["phone"], name="client_phone_idx"),
            models.Index(fields=["last_name", "first_name"], name="client_name_idx"),
        ]

    def __str__(self) -> str:
        return self.get_full_name()

    def get_full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def on_archive(self) -> None:
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


    def clean(self) -> None:
        super().clean()
        if not self.sponsor_client_id:
            return
        if self.pk and self.sponsor_client_id == self.pk:
            raise ValidationError({"sponsor_client": _("A client cannot sponsor themselves.")})

        visited: set[int] = set()
        current = self.sponsor_client
        while current is not None and current.pk:
            if self.pk and current.pk == self.pk:
                raise ValidationError({"sponsor_client": _("Sponsor relationship cannot create a cycle.")})
            if current.pk in visited:
                break
            visited.add(current.pk)
            current = current.sponsor_client

    def save(self, *args: Any, **kwargs: Any) -> None:
        update_fields = kwargs.get("update_fields")
        should_refresh_case_hash = update_fields is None or "case_number" in update_fields

        if should_refresh_case_hash:
            if self.case_number:
                self.case_number_hash = self.hash_case_number(cast(str, self.case_number))
            else:
                self.case_number_hash = None

        if update_fields is not None and "case_number" in update_fields:
            update_fields = set(update_fields)
            update_fields.add("case_number_hash")
            kwargs["update_fields"] = list(update_fields)

        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("clients:client_detail", kwargs={"pk": self.id})

    def get_application_purpose_display(self) -> str:
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
                    display_map[submission.slug] = str(localized).strip() if localized and str(localized).strip() else submission.name
                self._application_purpose_display_cache[language_code] = display_map
            if self.application_purpose in display_map:
                return display_map[self.application_purpose]

        return str(fallback)

    def get_document_requirement_purpose(self) -> str:
        if self.application_purpose == "family":
            if self.family_role in self.FAMILY_MEMBER_REQUIREMENT_PURPOSES:
                return str(self.family_role)
            if self.family_role == "sponsor":
                return "work"
        return str(self.application_purpose)

    def get_submitted_document_summary(self) -> dict[str, Any]:
        from clients.services.wniosek import build_submitted_document_summary

        return cast(dict[str, Any], build_submitted_document_summary(self))

    def get_submitted_document_codes(self) -> set[str]:
        summary = self.get_submitted_document_summary()
        return set(summary.get("codes", {}).keys())

    def get_document_checklist(self, check_file_existence: bool = False) -> list[dict[str, Any]]:
        from .document import DocumentRequirement, resolve_document_label
        from clients.services.document_helpers import document_file_exists

        current_language = translation.get_language() or self.language
        purpose = self.get_document_requirement_purpose()
        required_docs = DocumentRequirement.required_for(purpose, current_language)
        prefetched_documents = getattr(self, "_prefetched_objects_cache", {}).get("documents")
        
        uploaded_docs: list[Document] | models.QuerySet[Document]
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

        docs_map: dict[str, list[Document]] = {}
        for doc in uploaded_docs:
            setattr(doc, "_preloaded_version_count", getattr(doc, "preloaded_version_count", 0))
            setattr(doc, "_preloaded_requirement", req_map.get(doc.document_type))
            if check_file_existence:
                setattr(doc, "file_exists", document_file_exists(doc))
            docs_map.setdefault(doc.document_type, []).append(doc)

        submitted_summary = self.get_submitted_document_summary()
        submitted_by_code = submitted_summary.get("codes", {})
        custom_submissions = submitted_summary.get("custom", [])

        status_list: list[dict[str, Any]] = []
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

        prefetched_requirements = getattr(self, "_prefetched_objects_cache", {}).get("custom_document_requirements")
        if prefetched_requirements is None:
            custom_requirements = self.custom_document_requirements.filter(is_active=True).order_by("due_date", "created_at")
        else:
            custom_requirements = sorted(
                [requirement for requirement in prefetched_requirements if requirement.is_active],
                key=lambda requirement: (requirement.due_date or date.max, requirement.created_at),
            )

        for requirement in custom_requirements:
            documents = [
                document
                for document in docs_map.get(requirement.document_type, [])
                if getattr(document, "archived_at", None) is None
            ]
            status_list.append(
                {
                    "code": requirement.document_type,
                    "name": requirement.name,
                    "description": requirement.description,
                    "is_uploaded": bool(documents),
                    "is_submitted": False,
                    "is_complete": bool(documents) or not requirement.is_required,
                    "documents": documents,
                    "submitted_records": [],
                    "is_custom_submission": False,
                    "is_custom_requirement": True,
                    "custom_requirement": requirement,
                    "due_date": requirement.due_date,
                    "is_required": requirement.is_required,
                }
            )

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

    def get_document_name_by_code(self, doc_code: str) -> str:
        from .document import DocumentRequirement, get_available_document_types, resolve_document_label
        custom = self.custom_document_requirements.filter(document_type=doc_code).order_by("-is_active", "-id").first()
        if custom:
            return custom.name

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
                return str(item["label"])
        if doc_code in get_available_document_types(purpose):
            return str(resolve_document_label(doc_code, language=current_language))
        return doc_code.replace("_", " ").capitalize()

    def get_health_alerts(self, document_status_list: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        today = timezone.localdate()

        stats = (
            cast(Any, self.__class__.objects).filter(pk=self.pk)
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
            setattr(self, key, value)

        # Check legal stay expiration only if client hasn't submitted yet
        if self.workflow_stage in ["new_client", "document_collection"]:
            legal_stay_date = self.legal_basis_end_date
            if not legal_stay_date:
                try:
                    if hasattr(self, "mos_application_data") and self.mos_application_data.legal_stay_until:
                        legal_stay_date = self.mos_application_data.legal_stay_until
                except Exception:
                    pass

            if legal_stay_date:
                if legal_stay_date < today:
                    alerts.append(
                        {
                            "level": "danger",
                            "title": _("Основание пребывания уже истекло"),
                            "message": _("Проверьте основание пребывания и срочно свяжитесь с клиентом."),
                        }
                    )
                elif legal_stay_date <= today + timedelta(days=30):
                    alerts.append(
                        {
                            "level": "warning",
                            "title": _("Основание пребывания скоро истекает"),
                            "message": _("До окончания основания пребывания осталось меньше 30 дней."),
                        }
                    )

        if getattr(self, "health_awaiting_confirmation_count", 0):
            alerts.append(
                {
                    "level": "warning",
                    "title": _("Есть OCR-данные без подтверждения"),
                    "message": _("Документов с распознанными данными, ожидающими подтверждения: %(count)s.")
                    % {"count": self.health_awaiting_confirmation_count},
                    "action_label": _("Проверить OCR"),
                    "action_url": "#documentAccordion",
                }
            )

        if getattr(self, "health_expired_documents_count", 0):
            alerts.append(
                {
                    "level": "danger",
                    "title": _("Просроченные документы"),
                    "message": _("Просроченных документов: %(count)s.") % {"count": self.health_expired_documents_count},
                    "action_label": _("Открыть чеклист"),
                    "action_url": "#documentAccordion",
                }
            )

        if getattr(self, "health_expiring_documents_count", 0):
            alerts.append(
                {
                    "level": "warning",
                    "title": _("Истекающие документы"),
                    "message": _("Документов истекает в течение 7 дней: %(count)s.")
                    % {"count": self.health_expiring_documents_count},
                    "action_label": _("Открыть чеклист"),
                    "action_url": "#documentAccordion",
                }
            )

        if getattr(self, "health_wezwanie_count", 0) > 0 and not self.case_number:
            alerts.append(
                {
                    "level": "warning",
                    "title": _("Есть wezwanie без номера дела"),
                    "message": _("Проверьте распознавание или заполните case number вручную."),
                }
            )

        if self.fingerprints_date and not getattr(self, "health_appointment_email_sent_count", 0):
            alerts.append(
                {
                    "level": "warning",
                    "title": _("Не отправлено письмо по отпечаткам"),
                    "message": _("Дата fingerprints есть, но в истории нет appointment notification."),
                }
            )

        if getattr(self, "health_overdue_payments_count", 0):
            alerts.append(
                {
                    "level": "warning",
                    "title": _("Просроченные оплаты"),
                    "message": _("Оплат с due date сегодня или раньше: %(count)s.")
                    % {"count": self.health_overdue_payments_count},
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
                    "message": _("Не хватает обязательных документов: %(count)s.")
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
            family_group = getattr(self, 'family_group', None)
        except Exception:
            family_group = None
        if family_group is None and self.sponsor_client_id:
            try:
                family_group = getattr(self.sponsor_client, 'family_group', None)
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

        if getattr(self, "health_overdue_tasks_count", 0):
            alerts.append(
                {
                    "level": "danger",
                    "title": _("Есть просроченные задачи"),
                    "message": _("Просроченных задач: %(count)s.") % {"count": self.health_overdue_tasks_count},
                }
            )

        return alerts

    def get_workflow_summary(self, document_status_list: list[dict[str, Any]] | None = None) -> dict[str, Any]:
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
