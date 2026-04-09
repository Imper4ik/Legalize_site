from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class WniosekSubmission(models.Model):
    class DocumentKind(models.TextChoices):
        MAZOWIECKI_APPLICATION = "mazowiecki_application", _(
            "Mazowiecki application"
        )

    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="wniosek_submissions",
        verbose_name=_("Client"),
    )
    document_kind = models.CharField(
        max_length=64,
        choices=DocumentKind.choices,
        default=DocumentKind.MAZOWIECKI_APPLICATION,
        verbose_name=_("Document kind"),
    )
    attachment_count = models.PositiveIntegerField(default=0, verbose_name=_("Attachment count"))
    confirmed_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Confirmed at"))
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="confirmed_wniosek_submissions",
        verbose_name=_("Confirmed by"),
    )

    class Meta:
        ordering = ["-confirmed_at", "-id"]
        verbose_name = _("Wniosek submission")
        verbose_name_plural = _("Wniosek submissions")

    def __str__(self) -> str:
        return f"{self.client} / {self.get_document_kind_display()} / {self.confirmed_at:%Y-%m-%d %H:%M}"


class WniosekAttachment(models.Model):
    submission = models.ForeignKey(
        WniosekSubmission,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name=_("Submission"),
    )
    document_type = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Document type"),
    )
    entered_name = models.CharField(max_length=500, verbose_name=_("Entered name"))
    position = models.PositiveIntegerField(default=0, verbose_name=_("Position"))

    class Meta:
        ordering = ["position", "id"]
        verbose_name = _("Wniosek attachment")
        verbose_name_plural = _("Wniosek attachments")

    def __str__(self) -> str:
        return self.entered_name

    @property
    def is_custom(self) -> bool:
        return not bool(self.document_type)
