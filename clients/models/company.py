from __future__ import annotations

import re
import unicodedata

from django.db import models
from django.utils.translation import gettext_lazy as _


def normalize_company_name(value: str | None) -> str:
    """Return a conservative comparison key without changing the display name."""
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char)).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", text))


class Company(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Название компании"))
    normalized_name = models.CharField(max_length=255, blank=True, default="", db_index=True)
    nip = models.CharField(max_length=10, blank=True, default="", db_index=True, verbose_name="NIP")
    regon = models.CharField(max_length=14, blank=True, default="", db_index=True, verbose_name="REGON")
    krs = models.CharField(max_length=10, blank=True, default="", db_index=True, verbose_name="KRS")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))

    class Meta:
        verbose_name = _("Компания")
        verbose_name_plural = _("Компании")
        ordering = ["name"]

    def __str__(self) -> str:
        return str(self.name)

    def save(self, *args, **kwargs) -> None:
        self.name = " ".join((self.name or "").split())
        self.normalized_name = normalize_company_name(self.name)
        self.nip = re.sub(r"\D", "", self.nip or "")[:10]
        self.regon = re.sub(r"\D", "", self.regon or "")[:14]
        self.krs = re.sub(r"\D", "", self.krs or "")[:10]
        super().save(*args, **kwargs)
