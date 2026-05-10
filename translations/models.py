from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class TranslationOverride(models.Model):
    msgid = models.TextField(db_index=True, verbose_name=_("Original text (msgid)"))
    language = models.CharField(max_length=10, db_index=True, verbose_name=_("Language code"))
    text = models.TextField(blank=True, verbose_name=_("Translated text"))
    source = models.CharField(max_length=32, default="studio", verbose_name=_("Source"))
    is_active = models.BooleanField(default=True, verbose_name=_("Is active"))
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_("Updated by"),
    )

    class Meta:
        verbose_name = _("Translation Override")
        verbose_name_plural = _("Translation Overrides")
        unique_together = (("msgid", "language"),)
        indexes = [
            models.Index(fields=["language", "msgid"], name="trans_lang_msgid_idx"),
            models.Index(fields=["is_active", "language"], name="trans_active_lang_idx"),
        ]
        ordering = ["language", "msgid"]

    def __str__(self) -> str:
        return f"[{self.language}] {self.msgid[:30]}... -> {self.text[:30]}..."
