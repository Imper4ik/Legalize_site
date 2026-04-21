from django.db import models
from django.utils.translation import gettext_lazy as _


class AppSettings(models.Model):
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

    class Meta:
        verbose_name = _("Настройки приложения")
        verbose_name_plural = _("Настройки приложения")

    def __str__(self):
        return "App settings"

    @classmethod
    def get_solo(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj
