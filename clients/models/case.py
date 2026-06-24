from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Any, Self, cast
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from fernet_fields import EncryptedJSONField, EncryptedTextField
from legalize_site.soft_delete import SoftDeleteModel, SoftDeleteQuerySet


class CaseQuerySet(SoftDeleteQuerySet):
    def active_for_client(self, client_id: int) -> Self:
        return cast(Self, self.filter(client_id=client_id, archived_at__isnull=True))

    def active(self) -> Self:
        return cast(Self, self.filter(archived_at__isnull=True))

    def archived(self) -> Self:
        return cast(Self, self.filter(archived_at__isnull=False))


class CaseManager(models.Manager.from_queryset(CaseQuerySet)):  # type: ignore[misc]
    def get_queryset(self) -> CaseQuerySet:
        return cast(CaseQuerySet, super().get_queryset())

    def get_or_create_primary_for_client(self, client: Any) -> tuple[Case, bool]:
        case = self.filter(client=client, archived_at__isnull=True).order_by("opened_at", "id").first()
        if case is not None:
            return case, False
        return self.model.all_objects.create_from_client(client), True

    def get_or_create_primary_for_client_id(self, client_id: int) -> tuple[Case, bool]:
        case = self.filter(client_id=client_id, archived_at__isnull=True).order_by("opened_at", "id").first()
        if case is not None:
            return case, False
        from clients.models.client import Client

        client = Client.all_objects.get(pk=client_id)
        return self.model.all_objects.create_from_client(client), True


class CaseAllManager(models.Manager.from_queryset(CaseQuerySet)):  # type: ignore[misc]
    def create_from_client(self, client: Any) -> Case:
        with transaction.atomic():
            case = self.create(
                client=client,
                legacy_case_number=str(getattr(client, "case_number", "") or ""),
                needs_manual_number_check=True,
                internal_number="",
                authority_case_number="",
                status=getattr(client, "status", "new") or "new",
                workflow_stage=getattr(client, "workflow_stage", "new_client") or "new_client",
                application_purpose=getattr(client, "application_purpose", "") or "",
                basis_of_stay=getattr(client, "basis_of_stay", "") or "",
                submission_date=getattr(client, "submission_date", None),
                fingerprints_date=getattr(client, "fingerprints_date", None),
                fingerprints_time=getattr(client, "fingerprints_time", None),
                fingerprints_location=getattr(client, "fingerprints_location", "") or "",
                fingerprints_ticket=getattr(client, "fingerprints_ticket", "") or "",
                fingerprints_list=getattr(client, "fingerprints_list", "") or "",
                fingerprints_info=getattr(client, "fingerprints_info", "") or "",
                decision_date=getattr(client, "decision_date", None),
                assigned_staff=getattr(client, "assigned_staff", None),
                company=getattr(client, "company", None),
                is_test_data=getattr(client, "is_test_data", False),
                is_demo_data=getattr(client, "is_demo_data", False),
            )
            from clients.models.case import CaseParticipant
            CaseParticipant.objects.create(
                case=case,
                client=client,
                role="principal",
            )
            return case


class Case(SoftDeleteModel):
    STATUS_CHOICES = [
        ("new", _("Новый")),
        ("pending", _("В ожидании")),
        ("approved", _("Одобрен")),
        ("rejected", _("Отклонён")),
    ]
    WORKFLOW_STAGE_CHOICES = [
        ("new_client", _("Новый клиент")),
        ("document_collection", _("Сбор документов")),
        ("application_submitted", _("Подано в ужонд")),
        ("fingerprints", _("Ожидание отпечатков")),
        ("waiting_decision", _("Ожидание решения")),
        ("decision_received", _("Децизия")),
        ("closed", _("Закрыто")),
    ]

    uuid = models.UUIDField(default=uuid4, unique=True, editable=False, verbose_name=_("UUID дела"))
    client = models.ForeignKey("clients.Client", related_name="cases", on_delete=models.PROTECT)
    internal_number = EncryptedTextField(blank=True, default="", verbose_name=_("Внутренний номер дела"))
    authority_case_number = EncryptedTextField(blank=True, default="", verbose_name=_("Номер дела в уженде"))
    authority_case_number_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new", verbose_name=_("Статус"))
    workflow_stage = models.CharField(
        max_length=32,
        choices=WORKFLOW_STAGE_CHOICES,
        default="new_client",
        verbose_name=_("Этап workflow"),
    )
    application_purpose = models.CharField(max_length=64, blank=True, default="", verbose_name=_("Основание легализации"))
    application_type = models.CharField(max_length=64, blank=True, default="", verbose_name=_("Тип заявления"))
    basis_of_stay = models.CharField(max_length=100, blank=True, default="", verbose_name=_("Основание пребывания"))
    opened_at = models.DateField(default=timezone.localdate, verbose_name=_("Дата открытия дела"))
    submission_date = models.DateField(null=True, blank=True, verbose_name=_("Дата подачи"))
    fingerprints_date = models.DateField(null=True, blank=True, verbose_name=_("Дата отпечатков"))
    fingerprints_time = models.TimeField(null=True, blank=True, verbose_name=_("Время отпечатков"))
    fingerprints_location = models.CharField(max_length=255, blank=True, default="", verbose_name=_("Место отпечатков"))
    fingerprints_ticket = models.CharField(max_length=50, blank=True, default="", verbose_name=_("Номер билета"))
    fingerprints_list = models.CharField(max_length=100, blank=True, default="", verbose_name=_("Lista"))
    fingerprints_info = models.TextField(blank=True, default="", verbose_name=_("Информация об отпечатках"))
    decision = models.TextField(blank=True, default="", verbose_name=_("Решение"))
    decision_date = models.DateField(null=True, blank=True, verbose_name=_("Дата решения"))
    decision_valid_until = models.DateField(null=True, blank=True, verbose_name=_("Решение действительно до"))
    assigned_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_cases",
        verbose_name=_("Ответственный сотрудник"),
    )
    company = models.ForeignKey(
        "clients.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cases",
        verbose_name=_("Работодатель"),
    )
    new_card_application_data = EncryptedJSONField(default=dict, blank=True, verbose_name=_("Данные новой подачи"))
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Дата закрытия"))
    close_reason = models.TextField(blank=True, default="", verbose_name=_("Причина закрытия"))
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archived_cases",
        verbose_name=_("Архивировал"),
    )
    last_archive_batch_uuid = models.UUIDField(null=True, blank=True, db_index=True)
    version = models.PositiveIntegerField(default=1, verbose_name=_("Версия"))
    legacy_case_number = EncryptedTextField(blank=True, default="", verbose_name=_("Предыдущий номер дела"))
    needs_manual_number_check = models.BooleanField(default=False, verbose_name=_("Требуется ручная проверка номера"))
    migration_origin = models.CharField(max_length=40, null=True, blank=True, verbose_name=_("Источник миграции"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создано"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлено"))
    is_test_data = models.BooleanField(default=False, db_index=True)
    is_demo_data = models.BooleanField(default=False, db_index=True)

    objects = CaseManager()  # type: ignore[misc]
    all_objects = CaseAllManager()  # type: ignore[misc]

    class Meta:
        ordering = ["-opened_at", "-created_at", "-id"]
        verbose_name = _("Дело")
        verbose_name_plural = _("Дела")
        base_manager_name = "all_objects"
        indexes = [
            models.Index(fields=["client", "archived_at"], name="case_client_archived_idx"),
            models.Index(fields=["workflow_stage", "status"], name="case_workflow_status_idx"),
            models.Index(fields=["assigned_staff", "status"], name="case_staff_status_idx"),
            models.Index(fields=["opened_at"], name="case_opened_at_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "migration_origin"],
                condition=models.Q(migration_origin__isnull=False),
                name="unique_legacy_case_per_client",
            )
        ]

    def __str__(self) -> str:
        return f"{self.display_number} / {self.client}"

    def get_document_requirement_purpose(self, client: Any) -> str:
        participant = self.participants.filter(client=client).first()
        role = participant.role if participant else None
        if self.application_purpose == "family":
            if role in ["spouse", "child", "parent"]:
                return str(role)
            return "work"
        return str(self.application_purpose)

    def get_document_checklist(
        self,
        client: Any,
        check_file_existence: bool = False,
        requirements_cache: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        from django.utils import translation

        from clients.services.document_helpers import document_file_exists

        from .document import DocumentRequirement

        current_language = translation.get_language() or client.language
        purpose = self.get_document_requirement_purpose(client)

        if requirements_cache is not None:
            cache_key = f"{purpose}:{current_language}"
            if cache_key not in requirements_cache:
                required_docs = DocumentRequirement.required_for(purpose, current_language)
                reqs = list(DocumentRequirement.objects.filter(application_purpose=purpose))
                requirements_cache[cache_key] = (required_docs, reqs)
            required_docs, reqs = requirements_cache[cache_key]
        else:
            required_docs = DocumentRequirement.required_for(purpose, current_language)
            reqs = DocumentRequirement.objects.filter(application_purpose=purpose)

        uploaded_docs = self.documents.filter(client=client).annotate(
            preloaded_version_count=models.Count("versions")
        ).order_by("-uploaded_at")

        req_map = {r.document_type: r for r in reqs}

        docs_map: dict[str, list] = {}
        for doc in uploaded_docs:
            setattr(doc, "_preloaded_version_count", getattr(doc, "preloaded_version_count", 0))
            setattr(doc, "_preloaded_requirement", req_map.get(doc.document_type))
            if check_file_existence:
                setattr(doc, "file_exists", document_file_exists(doc))
            docs_map.setdefault(doc.document_type, []).append(doc)

        checklist = []
        seen_codes = set()
        for code, label in required_docs:
            doc_type = code
            docs = docs_map.get(doc_type, [])
            doc_obj = docs[0] if docs else None

            is_complete = False
            rejection_reason = ""
            is_awaiting_verification = False
            is_rejected = False
            is_verified = False

            if doc_obj:
                is_complete = bool(doc_obj.verified)
                rejection_reason = doc_obj.rejection_reason or ""
                is_verified = bool(doc_obj.verified)
                is_rejected = bool(doc_obj.rejection_reason and not doc_obj.verified)
                is_awaiting_verification = bool(not doc_obj.verified and not doc_obj.rejection_reason)

            checklist.append({
                "code": doc_type,
                "name": str(label),
                "label": str(label),
                "is_required": True,
                "is_complete": is_complete,
                "document": doc_obj,
                "documents": docs,
                "rejection_reason": rejection_reason,
                "is_awaiting_verification": is_awaiting_verification,
                "is_rejected": is_rejected,
                "is_verified": is_verified,
            })
            seen_codes.add(doc_type)

        prefetched_requirements = getattr(self, "_prefetched_objects_cache", {}).get("custom_document_requirements")
        if prefetched_requirements is None:
            custom_requirements = self.custom_document_requirements.filter(is_active=True).order_by("due_date", "created_at")
        else:
            from datetime import date as dt_date
            custom_requirements = sorted(
                [requirement for requirement in prefetched_requirements if requirement.is_active],
                key=lambda requirement: (requirement.due_date or dt_date.max, requirement.created_at),
            )

        for requirement in custom_requirements:
            docs = docs_map.get(requirement.document_type, [])
            doc_obj = docs[0] if docs else None
            is_complete = False
            rejection_reason = ""
            is_awaiting_verification = False
            is_rejected = False
            is_verified = False

            if doc_obj:
                is_complete = bool(doc_obj.verified)
                rejection_reason = doc_obj.rejection_reason or ""
                is_verified = bool(doc_obj.verified)
                is_rejected = bool(doc_obj.rejection_reason and not doc_obj.verified)
                is_awaiting_verification = bool(not doc_obj.verified and not doc_obj.rejection_reason)

            checklist.append({
                "code": requirement.document_type,
                "name": requirement.name,
                "label": requirement.name,
                "description": requirement.description,
                "is_required": requirement.is_required,
                "is_complete": is_complete or not requirement.is_required,
                "document": doc_obj,
                "documents": docs,
                "rejection_reason": rejection_reason,
                "is_awaiting_verification": is_awaiting_verification,
                "is_rejected": is_rejected,
                "is_verified": is_verified,
                "is_custom_requirement": True,
                "custom_requirement": requirement,
                "due_date": requirement.due_date,
            })
        return checklist

    def get_case_step(self, client: Any) -> int:
        mos_data = self.mos_application_data if hasattr(self, "mos_application_data") else None
        status = mos_data.status if mos_data else 'draft'

        if status == 'draft':
            return 1  # Выбор цели
        if status == 'client_filling':
            return 2  # Заполнение анкеты

        if status in ['client_completed', 'needs_correction', 'staff_review']:
            # Check checklist completion
            checklist = self.get_document_checklist(client, check_file_existence=False)
            has_missing_required = any(item.get("is_required") and not item.get("is_complete") for item in checklist)
            if has_missing_required:
                return 3  # Загрузка документов
            return 4  # Проверка сотрудником

        has_unpaid_payments = self.payments.filter(status__in=["pending", "partial"]).exists()

        if has_unpaid_payments and status in ['approved_by_staff', 'mos_package_ready']:
            return 5  # Оплата услуг

        if status in ['approved_by_staff', 'mos_package_ready']:
            return 6  # Подготовка пакета
        if status == 'submitted_in_mos':
            return 7  # Подача заявления
        if status == 'fingerprints':
            return 8  # Сдача отпечатков
        if status == 'waiting_decision':
            return 9  # Ожидание решения
        if status in ['decision_received', 'closed']:
            return 10  # Решение получено

        return 1

    APPLICATION_PURPOSE_CHOICES = [
        ("study", _("Учёба")),
        ("work", _("Работа")),
        ("family", _("Воссоединение с семьёй")),
    ]

    @property
    def display_number(self) -> str:
        """Human-facing case number.

        Only the authority (urzad) case number is a real working number. The
        UUID and the deprecated internal number must never be shown to staff;
        when no authority number exists yet we show a neutral placeholder.
        """
        number = str(self.authority_case_number or "").strip()
        return number or str(_("Дело без номера"))

    @property
    def has_authority_number(self) -> bool:
        return bool(str(self.authority_case_number or "").strip())

    def get_application_purpose_display(self) -> str:
        if not self.application_purpose:
            return ""
        return str(dict(self.APPLICATION_PURPOSE_CHOICES).get(self.application_purpose, self.application_purpose))

    @staticmethod
    def normalize_case_number(case_number: str) -> str:
        return case_number.strip().upper().replace(" ", "")

    @classmethod
    def hash_case_number(cls, case_number: str) -> str:
        normalized = cls.normalize_case_number(case_number)
        secret = str(getattr(settings, "SECRET_KEY", ""))
        return hmac.new(secret.encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()

    def save(self, *args: Any, **kwargs: Any) -> None:
        update_fields = kwargs.get("update_fields")
        should_refresh_case_hash = update_fields is None or "authority_case_number" in update_fields
        if should_refresh_case_hash:
            if self.authority_case_number:
                self.authority_case_number_hash = self.hash_case_number(cast(str, self.authority_case_number))
            else:
                self.authority_case_number_hash = ""
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("authority_case_number_hash")
                kwargs["update_fields"] = list(update_fields)
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("clients:case_detail", kwargs={"pk": self.pk})


class CaseArchiveSnapshot(models.Model):
    OBJECT_TYPE_DOCUMENT = "document"
    OBJECT_TYPE_PAYMENT = "payment"
    OBJECT_TYPE_REMINDER = "reminder"
    OBJECT_TYPE_TASK = "task"
    OBJECT_TYPE_PORTAL_USER = "portal_user"
    OBJECT_TYPE_CHOICES = [
        (OBJECT_TYPE_DOCUMENT, _("Документ")),
        (OBJECT_TYPE_PAYMENT, _("Платёж")),
        (OBJECT_TYPE_REMINDER, _("Напоминание")),
        (OBJECT_TYPE_TASK, _("Задача")),
        (OBJECT_TYPE_PORTAL_USER, _("Пользователь портала")),
    ]

    case = models.ForeignKey("clients.Case", on_delete=models.CASCADE, related_name="archive_snapshots")
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, related_name="case_archive_snapshots")
    archive_batch_uuid = models.UUIDField(db_index=True)
    object_type = models.CharField(max_length=32, choices=OBJECT_TYPE_CHOICES)
    object_id = models.PositiveBigIntegerField()
    was_active = models.BooleanField(default=True)
    previous_archived_at = models.DateTimeField(null=True, blank=True)
    previous_reminder_is_active = models.BooleanField(null=True, blank=True)
    previous_task_status = models.CharField(max_length=20, blank=True, default="")
    previous_user_is_active = models.BooleanField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="case_archive_snapshots",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["archive_batch_uuid", "object_type", "object_id"]
        indexes = [
            models.Index(fields=["case", "archive_batch_uuid"], name="case_snapshot_batch_idx"),
            models.Index(fields=["object_type", "object_id"], name="case_snapshot_object_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["archive_batch_uuid", "object_type", "object_id"],
                name="unique_case_archive_snapshot_object",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.archive_batch_uuid}: {self.object_type}#{self.object_id}"


class ClientArchiveBatch(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    client = models.ForeignKey("clients.Client", on_delete=models.PROTECT, related_name="archive_batches")
    archived_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="archived_client_batches")
    archived_at = models.DateTimeField(auto_now_add=True)
    restored_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="restored_client_batches")
    restored_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[("archived", "Архивировано"), ("restored", "Восстановлено")],
        default="archived",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["client"],
                condition=models.Q(status="archived"),
                name="one_open_archive_batch_per_client",
            )
        ]


class CaseArchiveBatch(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    case = models.ForeignKey(Case, on_delete=models.PROTECT, related_name="archive_batches")
    client_archive_batch = models.ForeignKey(
        ClientArchiveBatch,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="case_batches",
    )
    archived_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="archived_case_batches")
    archived_at = models.DateTimeField(auto_now_add=True)
    restored_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="restored_case_batches")
    restored_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[("archived", "Архивировано"), ("restored", "Восстановлено")],
        default="archived",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["case"],
                condition=models.Q(status="archived"),
                name="one_open_archive_batch_per_case",
            )
        ]


class CaseParticipant(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="participants")
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, related_name="case_participations")
    role = models.CharField(
        max_length=20,
        choices=[
            ("principal", "Главный заявитель"),
            ("spouse", "Супруг(а)"),
            ("child", "Ребенок"),
            ("parent", "Родитель"),
        ],
    )
    sponsor_participant = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sponsored_participants",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["case", "client"], name="unique_case_client_participant"),
            models.UniqueConstraint(
                fields=["case"],
                condition=models.Q(role="principal"),
                name="one_principal_per_case",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.sponsor_participant:
            if self.sponsor_participant.case_id != self.case_id:
                raise ValidationError("Спонсор должен принадлежать к тому же делу.")
            if self.sponsor_participant == self:
                raise ValidationError("Участник не может быть спонсором самого себя.")
        if self.role == "principal" and self.sponsor_participant is not None:
            raise ValidationError("Главный заявитель не может иметь спонсора.")
        if self.role == "principal" and self.case_id and self.client_id:
            if self.case.client_id != self.client_id:
                raise ValidationError("Клиент главного заявителя должен совпадать с основным клиентом дела.")



@receiver(post_save, sender="clients.Client")
def ensure_primary_case_for_client(sender: object, instance: Any, created: bool, raw: bool = False, **kwargs: object) -> None:
    if raw or not created or not getattr(instance, "pk", None):
        return
    Case.objects.get_or_create_primary_for_client(instance)
