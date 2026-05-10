from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

class TranslationOverride(models.Model):
    SOURCE_STUDIO = "studio"
    SOURCE_IMPORT = "import"
    SOURCE_MANUAL = "manual"

    SOURCE_CHOICES = [
        (SOURCE_STUDIO, _("Translation Studio")),
        (SOURCE_IMPORT, _("Imported from PO")),
        (SOURCE_MANUAL, _("Manual")),
    ]

    LANGUAGE_CHOICES = [
        ("ru", _("Russian")),
        ("pl", _("Polish")),
        ("en", _("English")),
    ]

    msgid = models.TextField(db_index=True, verbose_name=_("Original text (msgid)"))
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, db_index=True)
    text = models.TextField(blank=True, verbose_name=_("Translated text"))
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES, default=SOURCE_STUDIO)
    is_active = models.BooleanField(default=True, verbose_name=_("Is active"))
    
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="translation_override_updates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["msgid", "language"],
                name="unique_translation_override_msgid_lang",
            ),
        ]
        indexes = [
            models.Index(fields=["language", "msgid"], name="trans_lang_msgid_idx"),
            models.Index(fields=["is_active", "language"], name="trans_active_lang_idx"),
        ]
        ordering = ["language", "msgid"]
        verbose_name = _("Translation Override")
        verbose_name_plural = _("Translation Overrides")

    def __str__(self) -> str:
        return f"[{self.language}] {self.msgid[:30]}... -> {self.text[:30]}..."
