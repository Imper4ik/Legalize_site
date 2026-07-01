from __future__ import annotations

import hashlib
import hmac
import logging
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

from fernet_fields import EncryptedTextField
from legalize_site.soft_delete import SoftDeleteModel, SoftDeleteQuerySet

logger = logging.getLogger(__name__)


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
                family_role=(
                    getattr(client, "family_role", "") or ""
                    if getattr(client, "application_purpose", "") == "family"
                    else ""
                ),
                basis_of_stay=getattr(client, "basis_of_stay", "") or "",
                submission_date=getattr(client, "submission_date", None),
                fingerprints_date=getattr(client, "fingerprints_date", None),
                fingerprints_time=getattr(client, "fingerprints_time", None),
                fingerprints_location=getattr(client, "fingerprints_location", "") or "",
                fingerprints_ticket=getattr(client, "fingerprints_ticket", "") or "",
                fingerprints_list=getattr(client, "fingerprints_list", "") or "",
                fingerprints_info=getattr(client, "fingerprints_info", "") or "",
                decision_date=getattr(client, "decision_date", None),
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

    FAMILY_ROLE_SPONSOR = "sponsor"
    FAMILY_ROLE_SPOUSE = "family_spouse"
    FAMILY_ROLE_CHILD = "family_child"
    FAMILY_ROLE_CHOICES = [
        (FAMILY_ROLE_SPONSOR, _("Sponsor")),
        (FAMILY_ROLE_SPOUSE, _("Spouse")),
        (FAMILY_ROLE_CHILD, _("Child")),
    ]
    FAMILY_ROLE_VALUES = {FAMILY_ROLE_SPONSOR, FAMILY_ROLE_SPOUSE, FAMILY_ROLE_CHILD}

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
    family_role = models.CharField(
        max_length=32,
        blank=True,
        default="",
        choices=FAMILY_ROLE_CHOICES,
        verbose_name=_("Роль в семейном деле"),
    )
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
    company = models.ForeignKey(
        "clients.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cases",
        verbose_name=_("Работодатель"),
    )
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
            models.Index(fields=["opened_at"], name="case_opened_at_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "migration_origin"],
                condition=models.Q(migration_origin__isnull=False),
                name="unique_legacy_case_per_client",
            )
        ]

    def clean(self) -> None:
        super().clean()
        role = str(self.family_role or "").strip()
        purpose = str(self.application_purpose or "").strip()
        if role and role not in self.FAMILY_ROLE_VALUES:
            raise ValidationError({"family_role": _("Unknown family role.")})
        if purpose == "family" and not role:
            raise ValidationError({"family_role": _("Family role is required for family cases.")})
        if purpose != "family" and role:
            raise ValidationError({"family_role": _("Family role is only allowed for family cases.")})

    def __str__(self) -> str:
        return f"{self.display_number} / {self.client}"

    @property
    def display_number(self) -> str:
        """Staff-facing case number.

        Only the authority case number is a real working number. When it is not
        set yet, the migrated legacy number is shown as a fallback. The internal
        number is deprecated and the UUID must never be surfaced to staff, so a
        case with neither number shows a neutral placeholder instead
        (spec §3: authority → legacy → "Дело без номера").
        """
        number = str(self.authority_case_number or "").strip()
        if number:
            return number
        legacy = str(self.legacy_case_number or "").strip()
        if legacy:
            return legacy
        return str(_("Дело без номера"))

    def get_document_checklist(
        self,
        *,
        check_file_existence: bool = False,
        requirements_cache: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        from clients.services.case_context import build_case_document_checklist

        return build_case_document_checklist(
            self,
            check_file_existence=check_file_existence,
            requirements_cache=requirements_cache,
        )

    def get_application_purpose_display(self) -> str:
        """Localized purpose label; never a raw code like "work" (spec §15).

        Known purpose codes (study/work/family) are mapped to their localized
        labels; any other free-text basis is shown as entered.
        """
        from clients.models.client import Client

        choices = dict(Client.APPLICATION_PURPOSE_CHOICES)
        value = self.application_purpose or ""
        return str(choices.get(value, value))

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
        # Once the case has an authority number, the "case number missing" task
        # for this client is resolved (spec §4 — moved off Client.save).
        if self.authority_case_number and self.client_id:
            try:
                from clients.services.tasks import close_auto_task
                close_auto_task(self.client, "case_number_missing", case=self)
            except Exception:
                # Task auto-close is best-effort; never let it break the save.
                logger.exception(
                    "Failed to close case_number_missing task for client_id=%s", self.client_id
                )

    def get_absolute_url(self) -> str:
        return reverse("clients:case_detail", kwargs={"pk": self.pk})


class ClientArchiveBatch(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    client = models.ForeignKey("clients.Client", on_delete=models.PROTECT, related_name="archive_batches")
    archived_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="archived_client_batches")
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
    archived_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="archived_case_batches")
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
