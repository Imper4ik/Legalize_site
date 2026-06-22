from __future__ import annotations

import hashlib
import hmac
from typing import Any, Self, cast
from uuid import uuid4

import uuid
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from fernet_fields import EncryptedJSONField, EncryptedTextField
from legalize_site.soft_delete import SoftDeleteModel, SoftDeleteQuerySet
from clients.models.locking import OptimisticLockingMixin


class CaseQuerySet(SoftDeleteQuerySet):
    def active_for_client(self, client_id: int) -> Self:
        return cast(Self, self.filter(client_id=client_id, archived_at__isnull=True))


class CaseManager(models.Manager.from_queryset(CaseQuerySet)):  # type: ignore[misc]
    def get_queryset(self) -> CaseQuerySet:
        return cast(CaseQuerySet, super().get_queryset().active())

    def get_or_create_primary_for_client(self, client: Any) -> tuple[Case, bool]:
        case = self.filter(client=client).order_by("opened_at", "id").first()
        if case is not None:
            return case, False
        return self.model.all_objects.create_from_client(client), True

    def get_or_create_primary_for_client_id(self, client_id: int) -> tuple[Case, bool]:
        case = self.filter(client_id=client_id).order_by("opened_at", "id").first()
        if case is not None:
            return case, False
        from clients.models.client import Client

        client = Client.all_objects.get(pk=client_id)
        return self.model.all_objects.create_from_client(client), True


class CaseAllManager(models.Manager.from_queryset(CaseQuerySet)):  # type: ignore[misc]
    def create_from_client(self, client: Any) -> Case:
        return self.create(
            client=client,
            internal_number=str(getattr(client, "case_number", "") or ""),
            authority_case_number=str(getattr(client, "case_number", "") or ""),
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


class Case(OptimisticLockingMixin, SoftDeleteModel):
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

    @property
    def display_number(self) -> str:
        return str(self.internal_number or self.authority_case_number or self.uuid)

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
