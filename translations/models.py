from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class RuntimeTranslation(models.Model):
    """Database-backed translation override saved from Translation Studio.

    The normal Django `.po/.mo` catalogs remain the file-based baseline. This
    model stores runtime edits in PostgreSQL so Railway redeploys do not lose
    changes made from Translation Studio.
    """

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

    msgid = models.TextField(verbose_name=_("Source text / msgid"))
    language_code = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, db_index=True)
    msgstr = models.TextField(blank=True, verbose_name=_("Translated text / msgstr"))
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES, default=SOURCE_STUDIO)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runtime_translation_updates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["msgid", "language_code"],
                name="unique_runtime_translation_msgid_lang",
            ),
        ]
        indexes = [
            models.Index(fields=["language_code", "updated_at"], name="runtime_tr_lang_updated_idx"),
        ]
        ordering = ["msgid", "language_code"]
        verbose_name = _("Runtime translation")
        verbose_name_plural = _("Runtime translations")

    def __str__(self) -> str:
        preview = self.msgid.replace("\n", " ")[:80]
        return f"{self.language_code}: {preview}"
