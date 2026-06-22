"""Document version history model for tracking file replacements."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class DocumentVersion(models.Model):
    """Stores a historical snapshot of a document file before it was replaced."""

    document = models.ForeignKey(
        "clients.Document",
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name=_("Документ"),
    )
    case = models.ForeignKey(
        "clients.Case",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="document_versions",
        verbose_name=_("Дело"),
    )
    file = models.FileField(
        upload_to="document_versions/",
        verbose_name=_("Файл версии"),
    )
    version_number = models.PositiveIntegerField(
        verbose_name=_("Номер версии"),
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_("Загрузил"),
    )
    comment = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name=_("Комментарий"),
    )
    file_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Имя файла"),
    )
    file_size = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Размер файла (байт)"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Создано"),
    )

    class Meta:
        ordering = ["-version_number"]
        unique_together = ("document", "version_number")
        verbose_name = _("Версия документа")
        verbose_name_plural = _("Версии документов")
        indexes = [
            models.Index(fields=["document", "-version_number"], name="docver_doc_version_idx"),
            models.Index(fields=["case", "-version_number"], name="docver_case_version_idx"),
        ]

    def save(self, *args: object, **kwargs: object) -> None:
        update_fields = kwargs.get("update_fields")
        if self.case_id is None and self.document_id and self.document.case_id:
            self.case_id = self.document.case_id
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("case")
                kwargs["update_fields"] = list(update_fields)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"v{self.version_number} — {self.document}"

    @property
    def uploader_display(self) -> str:
        if not self.uploaded_by:
            return str(_("Система"))
        full_name = self.uploaded_by.get_full_name().strip()
        return full_name or getattr(self.uploaded_by, "email", str(self.uploaded_by))
