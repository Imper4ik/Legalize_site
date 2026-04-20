from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class DocumentProcessingJob(models.Model):
    JOB_TYPE_WEZWANIE_OCR = "wezwanie_ocr"

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    JOB_TYPE_CHOICES = [
        (JOB_TYPE_WEZWANIE_OCR, _("Wezwanie OCR")),
    ]
    STATUS_CHOICES = [
        (STATUS_PENDING, _("Pending")),
        (STATUS_PROCESSING, _("Processing")),
        (STATUS_COMPLETED, _("Completed")),
        (STATUS_FAILED, _("Failed")),
    ]

    document = models.ForeignKey(
        "clients.Document",
        on_delete=models.CASCADE,
        related_name="processing_jobs",
        verbose_name=_("Document"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="document_processing_jobs",
        verbose_name=_("Created by"),
    )
    job_type = models.CharField(
        max_length=50,
        choices=JOB_TYPE_CHOICES,
        default=JOB_TYPE_WEZWANIE_OCR,
        verbose_name=_("Job type"),
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name=_("Status"),
    )
    source_file_name = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name=_("Source file name"),
    )
    attempts = models.PositiveIntegerField(default=0, verbose_name=_("Attempts"))
    error_message = models.TextField(blank=True, default="", verbose_name=_("Error message"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Started at"))
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Completed at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    class Meta:
        ordering = ["created_at"]
        unique_together = ("document", "job_type")
        verbose_name = _("Document processing job")
        verbose_name_plural = _("Document processing jobs")

    def __str__(self) -> str:
        return f"{self.job_type} for document {self.document_id} ({self.status})"
