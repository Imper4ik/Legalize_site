from __future__ import annotations

from typing import Any, Self

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from clients.models.consistency import assert_case_client_consistent


class ReminderQuerySet(models.QuerySet):
    def for_active_cases(self) -> Self:
        return self.filter(case__isnull=False, case__archived_at__isnull=True)


class Reminder(models.Model):
    objects = models.Manager.from_queryset(ReminderQuerySet)()

    REMINDER_TYPE_CHOICES = [
        ('payment', _('Оплата')),
        ('document', _('Документ')),
        ('legal_stay', _('Легальное пребывание')),
        ('other', _('Другое')),
    ]

    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE, related_name='reminders', verbose_name=_("Клиент"))
    case = models.ForeignKey(
        'clients.Case',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reminders',
        verbose_name=_("Дело"),
    )
    payment = models.OneToOneField('clients.Payment', on_delete=models.CASCADE, null=True, blank=True, related_name="reminder")
    document = models.OneToOneField('clients.Document', on_delete=models.CASCADE, null=True, blank=True, related_name="reminder")
    custom_document_requirement = models.ForeignKey(
        "clients.ClientDocumentRequirement",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reminders",
    )
    reminder_type = models.CharField(max_length=20, choices=REMINDER_TYPE_CHOICES, default='document',
                                     verbose_name=_("Тип напоминания"))
    title = models.CharField(max_length=255, verbose_name=_("Заголовок напоминания"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("Детали"))
    due_date = models.DateField(verbose_name=_("Ключевая дата"))
    is_active = models.BooleanField(default=True, verbose_name=_("Активно"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1, verbose_name=_("Версия"))

    @property
    def display_title(self) -> str:
        if self.custom_document_requirement:
            return gettext("Нужно предоставить документ: %(name)s") % {
                "name": self.custom_document_requirement.name
            }
        if self.reminder_type == 'document' and self.document:
            return gettext("Проверьте срок действия документа: %(name)s") % {
                "name": self.document.display_name
            }
        if self.reminder_type == 'payment' and self.payment:
            return gettext("Срок оплаты наступил: %(service)s") % {
                "service": self.payment.get_service_description_display()
            }
        if self.reminder_type == 'legal_stay':
            due_str = self.due_date.strftime('%d.%m.%Y') if self.due_date else ""
            return gettext("Срок подачи по легальному пребыванию: %(date)s") % {
                "date": due_str
            }
        return self.title

    @property
    def display_notes(self) -> str:
        if self.custom_document_requirement:
            return self.custom_document_requirement.description or self.notes or ""
        if self.reminder_type == 'document' and self.document:
            expiry_str = self.document.expiry_date.strftime('%d.%m.%Y') if self.document.expiry_date else ""
            return gettext("Срок действия документа клиента %(client)s: %(date)s.") % {
                "client": str(self.client),
                "date": expiry_str
            }
        if self.reminder_type == 'payment' and self.payment:
            total_str = f"{self.payment.total_amount:.2f}"
            due_str = f"{self.payment.amount_due:.2f}"
            return gettext("Сумма услуги: %(total)s; осталось оплатить: %(due)s; клиент: %(client)s.") % {
                "total": total_str,
                "due": due_str,
                "client": str(self.client),
            }
        if self.reminder_type == 'legal_stay' and self.client:
            try:
                mos = self.client.mos_applications.first()
                if mos and mos.legal_stay_until:
                    stay_str = mos.legal_stay_until.strftime('%d.%m.%Y')
                    due_str = self.due_date.strftime('%d.%m.%Y') if self.due_date else ""
                    return gettext("Легальное пребывание до: %(stay_until)s. Рекомендуемый срок подачи с учетом выходных: %(due_date)s.") % {
                        "stay_until": stay_str,
                        "due_date": due_str
                    }
            except AttributeError:
                return self.notes or ""
        return self.notes or ""

    def _resolve_source_case_id(self) -> int | None:
        """Case id implied by the reminder's source object, if any (payment first)."""
        for source in (self.payment, self.document, self.custom_document_requirement):
            if source is not None and source.case_id:
                return source.case_id
        return None

    def clean(self) -> None:
        super().clean()
        source_case_id = self._resolve_source_case_id()

        if self.case_id is None:
            if source_case_id is not None:
                self.case_id = source_case_id
            elif self.client_id:
                from clients.models.consistency import resolve_required_case
                try:
                    self.case = resolve_required_case(self.client_id, self.__class__.__name__)
                except ValidationError as e:
                    raise ValidationError(e.message)
            else:
                raise ValidationError("Case is required.")

        if self.case_id and self.client_id and self.case and self.case.client_id != self.client_id:
            raise ValidationError("Клиент и дело не согласованы.")

        errors: dict[str, list[Any]] = {}
        sources = [
            source
            for source in (self.payment, self.document, self.custom_document_requirement)
            if source is not None
        ]
        if len(sources) > 1:
            errors.setdefault("__all__", []).append(_("Reminder cannot point to multiple source objects."))

        payment = self.payment
        if payment is not None:
            if self.client_id and payment.client_id != self.client_id:
                errors.setdefault("payment", []).append(_("Payment reminder must belong to the same client."))
            if self.case_id and payment.case_id and payment.case_id != self.case_id:
                errors.setdefault("payment", []).append(_("Payment reminder must belong to the same case."))
            if self.reminder_type != "payment":
                errors.setdefault("reminder_type", []).append(_("Payment source requires payment reminder type."))

        document = self.document
        if document is not None:
            if self.client_id and document.client_id != self.client_id:
                errors.setdefault("document", []).append(_("Document reminder must belong to the same client."))
            if self.case_id and document.case_id and document.case_id != self.case_id:
                errors.setdefault("document", []).append(_("Document reminder must belong to the same case."))
            if self.reminder_type != "document":
                errors.setdefault("reminder_type", []).append(_("Document source requires document reminder type."))

        requirement = self.custom_document_requirement
        if requirement is not None:
            if self.client_id and requirement.client_id != self.client_id:
                errors.setdefault("custom_document_requirement", []).append(
                    _("Custom document reminder must belong to the same client.")
                )
            if self.case_id and requirement.case_id and requirement.case_id != self.case_id:
                errors.setdefault("custom_document_requirement", []).append(
                    _("Custom document reminder must belong to the same case.")
                )
            if self.reminder_type != "document":
                errors.setdefault("reminder_type", []).append(_("Custom document source requires document reminder type."))

        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        update_fields = kwargs.get("update_fields")
        source_case_id = self._resolve_source_case_id()

        if self.case_id is None:
            if source_case_id is not None:
                self.case_id = source_case_id
            elif self.client_id:
                from clients.models.consistency import resolve_required_case
                self.case = resolve_required_case(self.client_id, self.__class__.__name__)
            if self.case_id is not None and update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("case")
                kwargs["update_fields"] = list(update_fields)
        assert_case_client_consistent(self)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Напоминание для {self.client}: {self.title}"

    class Meta:
        ordering = ['due_date']
        indexes = [
            models.Index(fields=["is_active", "due_date"], name="reminder_active_due_idx"),
            models.Index(fields=["client", "is_active"], name="reminder_client_active_idx"),
            models.Index(fields=["case", "is_active"], name="reminder_case_active_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~(models.Q(payment__isnull=False) & models.Q(document__isnull=False)),
                name="reminder_not_payment_and_document",
            ),
            models.CheckConstraint(
                condition=~(models.Q(payment__isnull=False) & models.Q(custom_document_requirement__isnull=False)),
                name="reminder_not_payment_and_custom",
            ),
            models.CheckConstraint(
                condition=~(models.Q(document__isnull=False) & models.Q(custom_document_requirement__isnull=False)),
                name="reminder_not_document_and_custom",
            ),
            models.CheckConstraint(
                condition=~(models.Q(reminder_type='legal_stay') & (models.Q(payment__isnull=False) | models.Q(document__isnull=False) | models.Q(custom_document_requirement__isnull=False))),
                name="reminder_legal_stay_no_source",
            ),
            models.CheckConstraint(
                condition=~(models.Q(reminder_type='payment') & models.Q(payment__isnull=True)),
                name="reminder_payment_type_requires_payment",
            ),
            models.CheckConstraint(
                condition=~(models.Q(reminder_type='document') & models.Q(document__isnull=True) & models.Q(custom_document_requirement__isnull=True)),
                name="reminder_document_type_requires_source",
            ),
        ]
