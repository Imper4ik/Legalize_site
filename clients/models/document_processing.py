from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class DocumentProcessingJob(models.Model):
    JOB_TYPE_WEZWANIE_OCR = "wezwanie_ocr"
    JOB_TYPE_COMPANY_DOC_OCR = "company_doc_ocr"
    JOB_TYPE_PASSPORT_OCR = "passport_ocr"
    JOB_TYPE_RENTAL_OCR = "rental_ocr"
    JOB_TYPE_ZUS_OCR = "zus_ocr"
    JOB_TYPE_INSURANCE_OCR = "insurance_ocr"

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    JOB_TYPE_CHOICES = [
        (JOB_TYPE_WEZWANIE_OCR, _("Wezwanie OCR")),
        (JOB_TYPE_COMPANY_DOC_OCR, _("Company Doc OCR")),
        (JOB_TYPE_PASSPORT_OCR, _("Passport OCR")),
        (JOB_TYPE_RENTAL_OCR, _("Rental Agreement OCR")),
        (JOB_TYPE_ZUS_OCR, _("ZUS Documents OCR")),
        (JOB_TYPE_INSURANCE_OCR, _("Insurance Policy OCR")),
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
    case = models.ForeignKey(
        "clients.Case",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="document_processing_jobs",
        verbose_name=_("Case"),
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
    max_attempts = models.PositiveIntegerField(default=3, verbose_name=_("Max attempts"))
    error_message = models.TextField(blank=True, default="", verbose_name=_("Error message"))
    next_attempt_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Next attempt at"))
    lease_expires_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Lease expires at"))
    is_demo_data = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Started at"))
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Completed at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))
    requires_confirmation = models.BooleanField(default=False, verbose_name=_("Requires confirmation"))

    class Meta:
        ordering = ["created_at"]
        unique_together = ("document", "job_type")
        indexes = [
            models.Index(fields=["job_type", "status", "next_attempt_at"], name="docjob_ready_idx"),
            models.Index(fields=["case", "status"], name="docjob_case_status_idx"),
            models.Index(fields=["status", "lease_expires_at"], name="docjob_lease_idx"),
        ]
        verbose_name = _("Document processing job")
        verbose_name_plural = _("Document processing jobs")

    def _document_case_id(self) -> int | None:
        if not self.document_id:
            return None
        cached_document = self._state.fields_cache.get("document")
        if cached_document is not None:
            return cached_document.case_id
        from clients.models import Document

        return Document.all_objects.filter(pk=self.document_id).values_list("case_id", flat=True).first()

    def clean(self) -> None:
        super().clean()
        document_case_id = self._document_case_id()
        if self.case_id is not None and document_case_id is not None and self.case_id != document_case_id:
            raise ValidationError({"case": _("OCR job case must match the document case.")})

    def save(self, *args: Any, **kwargs: Any) -> None:
        update_fields = kwargs.get("update_fields")
        document_case_id = self._document_case_id()
        if self.case_id is None and document_case_id:
            self.case_id = document_case_id
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("case")
                kwargs["update_fields"] = list(update_fields)
        elif self.case_id is not None and document_case_id is not None and self.case_id != document_case_id:
            raise ValidationError({"case": _("OCR job case must match the document case.")})
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.job_type} for document {self.document_id} ({self.status})"
