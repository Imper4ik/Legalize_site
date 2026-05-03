from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _


class FamilyGroup(models.Model):
    sponsor = models.OneToOneField(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="family_group",
        verbose_name=_("Спонсор"),
    )
    sponsor_monthly_income = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Доход спонсора"),
    )
    monthly_support_per_person = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("823.00"),
        verbose_name=_("Ежемесячное содержание"),
    )
    monthly_housing_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Стоимость жилья"),
    )
    meldunek_free_housing = models.BooleanField(
        default=False,
        verbose_name=_("Meldunek / бесплатное жильё"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создано"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлено"))

    class Meta:
        verbose_name = _("Семейная группа")
        verbose_name_plural = _("Семейные группы")

    def __str__(self) -> str:
        return f"{self.sponsor} — {self._meta.verbose_name}"
