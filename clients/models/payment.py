from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Self

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from clients.models.consistency import assert_case_client_consistent
from legalize_site.soft_delete import SoftDeleteModel, SoftDeleteQuerySet


class PaymentQuerySet(SoftDeleteQuerySet):
    def for_active_cases(self) -> Self:
        return self.filter(case__isnull=False, case__archived_at__isnull=True)


class PaymentManager(models.Manager.from_queryset(PaymentQuerySet)):  # type: ignore[misc]
    def get_queryset(self) -> PaymentQuerySet:
        return super().get_queryset().active()


class Payment(SoftDeleteModel):
    objects = PaymentManager()  # type: ignore[misc]
    all_objects = PaymentQuerySet.as_manager()  # type: ignore[misc]

    PAYMENT_STATUS_CHOICES = [
        ("pending", _("Ожидает оплаты")),
        ("partial", _("Частично оплачен")),
        ("paid", _("Оплачен полностью")),
        ("refunded", _("Возврат")),
    ]
    PAYMENT_METHOD_CHOICES = [
        ("card", _("Карта")),
        ("cash", _("Наличные")),
        ("transfer", _("Перевод")),
        ("blik", _("BLIK")),
    ]
    SERVICE_CHOICES = [
        ("work_service", _("Работа")),
        ("study_service", _("Учёба")),
        ("consultation", _("Консультация")),
    ]

    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, related_name="payments", verbose_name=_("Клиент"))
    case = models.ForeignKey(
        "clients.Case",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payments",
        verbose_name=_("Дело"),
    )
    service_description = models.CharField(max_length=100, choices=SERVICE_CHOICES, verbose_name=_("Описание услуги"))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Общая сумма"))
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_("Оплаченная сумма"))
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default="pending", verbose_name=_("Статус оплаты"))
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, blank=True, null=True, verbose_name=_("Способ оплаты"))
    payment_date = models.DateField(blank=True, null=True, verbose_name=_("Дата оплаты"))
    due_date = models.DateField(blank=True, null=True, verbose_name=_("Срок оплаты"))
    transaction_id = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("ID транзакции"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создано"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлено"))
    version = models.PositiveIntegerField(default=1, verbose_name=_("Версия"))

    is_test_data = models.BooleanField(default=False, db_index=True)
    is_demo_data = models.BooleanField(default=False, db_index=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        update_fields = kwargs.get("update_fields")
        if self.case_id is None and self.client_id:
            from clients.models.consistency import resolve_required_case
            self.case = resolve_required_case(self.client_id, self.__class__.__name__)
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("case")
                kwargs["update_fields"] = list(update_fields)
        assert_case_client_consistent(self)
        super().save(*args, **kwargs)

    @property
    def amount_due(self) -> Decimal:
        total = Decimal(str(self.total_amount)) if self.total_amount is not None else Decimal("0.00")
        paid = Decimal(str(self.amount_paid)) if self.amount_paid is not None else Decimal("0.00")
        return total - paid

    def clean(self) -> None:
        super().clean()
        if self.case_id is None:
            if self.client_id:
                from clients.models.consistency import resolve_required_case
                try:
                    self.case = resolve_required_case(self.client_id, self.__class__.__name__)
                except ValidationError as e:
                    raise ValidationError(e.message)
            else:
                raise ValidationError("Case is required.")
        if self.case_id and self.client_id and self.case and self.case.client_id != self.client_id:
            raise ValidationError("Клиент и дело не согласованы.")

        errors: dict[str, list[str]] = {}
        raw_total_amount = self.total_amount
        raw_amount_paid = self.amount_paid

        def _as_decimal(value: object) -> Decimal | None:
            if value is None:
                return None
            if isinstance(value, Decimal):
                return value
            try:
                return Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError):
                return None

        total_amount = _as_decimal(raw_total_amount)
        amount_paid = _as_decimal(raw_amount_paid)

        if raw_amount_paid is None:
            amount_paid = Decimal("0.00")
            self.amount_paid = amount_paid
        elif amount_paid is None:
            return

        if total_amount is None:
            return

        if total_amount < Decimal("0.00"):
            errors.setdefault("total_amount", []).append("Total amount cannot be negative.")

        if amount_paid < Decimal("0.00"):
            errors.setdefault("amount_paid", []).append("Amount paid cannot be negative.")

        if amount_paid > total_amount:
            errors.setdefault("amount_paid", []).append("Amount paid cannot exceed total amount.")

        if self.status == "paid" and amount_paid != total_amount:
            errors.setdefault("amount_paid", []).append("Paid payments must have amount paid equal to total amount.")
        if self.status == "partial" and not (Decimal("0.00") < amount_paid < total_amount):
            errors.setdefault("amount_paid", []).append("Partial payments must be greater than zero and below total amount.")
        if self.status == "pending" and amount_paid != Decimal("0.00"):
            errors.setdefault("amount_paid", []).append("Pending payments cannot have a paid amount.")

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"Счёт {self.pk} - {self.client} ({self.total_amount} PLN)"

    def on_archive(self) -> None:
        reminder = getattr(self, "reminder", None)
        if reminder is not None:
            reminder.is_active = False
            reminder.save(update_fields=["is_active"])

    def on_restore(self) -> None:
        reminder = getattr(self, "reminder", None)
        if self.status == "partial" and self.due_date and reminder is not None:
            reminder.is_active = True
            reminder.save(update_fields=["is_active"])

    class Meta:
        ordering = ["-created_at"]
        base_manager_name = "all_objects"
        indexes = [
            models.Index(fields=["client", "status"], name="payment_client_status_idx"),
            models.Index(fields=["case", "status"], name="payment_case_status_idx"),
            models.Index(fields=["status", "due_date"], name="payment_status_due_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(total_amount__gte=0),
                name="payment_total_amount_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(amount_paid__gte=0),
                name="payment_amount_paid_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(amount_paid__lte=models.F("total_amount")),
                name="payment_amount_paid_lte_total",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="pending") | models.Q(amount_paid=0),
                name="payment_pending_amount_zero",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="paid") | models.Q(amount_paid=models.F("total_amount")),
                name="payment_paid_amount_matches_total",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="partial")
                | (models.Q(amount_paid__gt=0) & models.Q(amount_paid__lt=models.F("total_amount"))),
                name="payment_partial_amount_between",
            ),
        ]
        verbose_name = _("Платёж")
        verbose_name_plural = _("Платежи")
