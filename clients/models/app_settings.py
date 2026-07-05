from __future__ import annotations

from typing import Self, cast

from django.db import models
from django.utils.translation import gettext_lazy as _


class AppSettings(models.Model):
    organization_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Название организации"),
    )
    contact_email = models.EmailField(
        blank=True,
        default="",
        verbose_name=_("Контактный email"),
    )
    contact_phone = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name=_("Контактный телефон"),
    )
    office_address = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Адрес офиса"),
        help_text=_("Одна строка на строку. Используется как общий адрес текущей базы."),
    )
    default_proxy_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Имя pełnomocnika по умолчанию"),
    )
    mazowiecki_office_template = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Mazowiecki: адрес urzedu"),
        help_text=_("Одна строка на строку. Подставляется по умолчанию в шаблон wniosek mazowiecki для всей базы."),
    )
    mazowiecki_proxy_template = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Mazowiecki: pelnomocnik"),
        help_text=_("Одна строка на строку. Подставляется по умолчанию в шаблон wniosek mazowiecki для всей базы."),
    )

    # --- Реквизиты администратора данных (RODO / GDPR art. 13) ---
    # Кто является контролёром персональных данных: юр. лицо и его представитель.
    # Значения редактируются клиентом в интерфейсе и подставляются в информационную
    # оговорку и запись согласия вместо хардкода.
    legal_entity_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Администратор данных (юр. лицо)"),
        help_text=_("Полное юридическое наименование администратора персональных данных."),
    )
    data_controller_nip = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name=_("NIP"),
    )
    data_controller_regon = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name=_("REGON"),
    )
    data_controller_krs = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name=_("KRS"),
    )
    legal_address = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Юридический адрес"),
        help_text=_("Одна строка на строку. Юридический адрес администратора данных."),
    )
    representative_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Представитель"),
        help_text=_("ФИО и должность лица, представляющего администратора данных."),
    )
    dpo_contact = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Контакт инспектора по защите данных (IOD/DPO)"),
        help_text=_("Email или иной контакт инспектора по защите данных, если назначен."),
    )
    privacy_policy_version = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name=_("Версия политики конфиденциальности"),
        help_text=_(
            "Например, 2026-01. Фиксируется в записи согласия, чтобы можно было "
            "доказать, с какой редакцией политики согласился субъект данных."
        ),
    )
    privacy_policy_body = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Текст политики конфиденциальности"),
        help_text=_(
            "Необязательно. Дополнительный текст политики, который показывается "
            "на публичной странице под стандартными разделами RODO."
        ),
    )
    data_retention_summary = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Срок хранения данных"),
        help_text=_("Кратко: как долго хранятся данные. Показывается в политике."),
    )

    class Meta:
        verbose_name = _("Настройки приложения")
        verbose_name_plural = _("Настройки приложения")

    def __str__(self) -> str:
        return "App settings"

    @classmethod
    def get_solo(cls) -> Self:
        obj, _created = cls.objects.get_or_create(pk=1)
        return cast(Self, obj)
