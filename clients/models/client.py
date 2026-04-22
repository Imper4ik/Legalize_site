import hashlib
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext, gettext_lazy as _
from fernet_fields import EncryptedTextField

from clients.constants import DocumentType
from legalize_site.soft_delete import SoftDeleteModel


class Client(SoftDeleteModel):
    APPLICATION_PURPOSE_CHOICES = [
        ("study", _("Учёба")),
        ("work", _("Работа")),
        ("family", _("Воссоединение семьи")),
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
    decision_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Дата официальной децизии"),
    )
    notes = models.TextField(blank=True, null=True, verbose_name=_("Uwagi / Заметки"))
    has_checklist_access = models.BooleanField(default=False, verbose_name=_("Доступ к чеклисту предоставлен"))

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
        on_delete=models.CASCADE,
        related_name="client_profile",
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def on_archive(self):
        if not self.user_id:
            return
        user = type(self.user).objects.filter(pk=self.user_id).first() if hasattr(type(self), "user") else None
        if user is None:
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

        if self.application_purpose:
            submission = Submission.objects.filter(slug=self.application_purpose).first()
            if submission:
                return submission.localized_name

        return dict(self.APPLICATION_PURPOSE_CHOICES).get(self.application_purpose, self.application_purpose or "")

    def get_submitted_document_summary(self):
        from clients.services.wniosek import build_submitted_document_summary

        return build_submitted_document_summary(self)

    def get_submitted_document_codes(self) -> set[str]:
        summary = self.get_submitted_document_summary()
        return set(summary.get("codes", {}).keys())

    def get_document_checklist(self):
        from .document import DocumentRequirement, resolve_document_label

        current_language = translation.get_language() or self.language
        required_docs = DocumentRequirement.required_for(self.application_purpose, current_language)
        uploaded_docs = self.documents.all().order_by("-uploaded_at")

        docs_map = {}
        for doc in uploaded_docs:
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
        catalog = DocumentRequirement.catalog_for(
            self.application_purpose,
            current_language,
            include_optional=True,
            include_fallback=True,
        )
        for item in catalog:
            if item["code"] == doc_code:
                return item["label"]
        if doc_code in get_available_document_types(self.application_purpose):
            return resolve_document_label(doc_code, language=current_language)
        return doc_code.replace("_", " ").capitalize()

    def get_health_alerts(self, document_status_list=None):
        alerts = []
        today = timezone.localdate()

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

        awaiting_confirmation_count = self.documents.filter(awaiting_confirmation=True).count()
        if awaiting_confirmation_count:
            alerts.append(
                {
                    "level": "warning",
                    "title": _("Есть документы без подтверждения"),
                    "message": _("Документов, ожидающих подтверждения: %(count)s.")
                    % {"count": awaiting_confirmation_count},
                }
            )

        wezwanie_exists = self.documents.filter(
            document_type__in=[DocumentType.WEZWANIE, DocumentType.WEZWANIE.value]
        ).exists()
        if wezwanie_exists and not self.case_number:
            alerts.append(
                {
                    "level": "warning",
                    "title": _("Есть wezwanie без номера дела"),
                    "message": _("Проверьте распознавание или заполните case number вручную."),
                }
            )

        if self.fingerprints_date and not self.email_logs.filter(
            template_type="appointment_notification"
        ).exists():
            alerts.append(
                {
                    "level": "warning",
                    "title": _("Не отправлено письмо по отпечаткам"),
                    "message": _("Дата fingerprints есть, но в истории нет appointment notification."),
                }
            )

        payments_without_reminders = self.payments.filter(status__in=["pending", "partial"]).exclude(
            reminder__is_active=True
        ).count()
        if payments_without_reminders:
            alerts.append(
                {
                    "level": "warning",
                    "title": _("Есть оплаты без reminder"),
                    "message": _("Платежей без активного reminder: %(count)s.")
                    % {"count": payments_without_reminders},
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
                }
            )

        overdue_tasks_count = self.staff_tasks.filter(
            status__in=["open", "in_progress"],
            due_date__lt=today,
        ).count()
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
        open_tasks = self.staff_tasks.filter(status__in=["open", "in_progress"])
        overdue_tasks = open_tasks.filter(due_date__lt=timezone.localdate()).count()
        return {
            "stage_label": self.get_workflow_stage_display(),
            "alerts": alerts,
            "alerts_count": len(alerts),
            "open_tasks_count": open_tasks.count(),
            "overdue_tasks_count": overdue_tasks,
        }
