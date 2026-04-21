from django.db import models
from django.utils.translation import gettext_lazy as _


class Company(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Название компании"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))

    class Meta:
        verbose_name = _("Компания")
        verbose_name_plural = _("Компании")
        ordering = ["name"]

    def __str__(self):
        return self.name
