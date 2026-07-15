from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class CaseEmployerAssignment(models.Model):
    case = models.ForeignKey("clients.Case", on_delete=models.PROTECT, related_name="employer_assignments")
    company = models.ForeignKey("clients.Company", on_delete=models.PROTECT, related_name="case_assignments")
    effective_from = models.DateField(null=True, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=32, blank=True, default="manual")
    source_document = models.ForeignKey(
        "clients.Document", on_delete=models.SET_NULL, null=True, blank=True, related_name="employer_assignments"
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="confirmed_employer_assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["case"], condition=Q(ended_at__isnull=True), name="one_active_employer_per_case"
            )
        ]


class EmployerChangeCandidate(models.Model):
    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_SAME = "same"
    STATUS_OCR_ERROR = "ocr_error"
    STATUS_NEEDS_INFO = "needs_info"
    STATUS_DEFERRED = "deferred"
    STATUS_CHOICES = [
        (STATUS_PENDING, _("Ожидает проверки")),
        (STATUS_CONFIRMED, _("Новый работодатель подтверждён")),
        (STATUS_SAME, _("Тот же работодатель")),
        (STATUS_OCR_ERROR, _("Ошибка распознавания")),
        (STATUS_NEEDS_INFO, _("Нужна информация")),
        (STATUS_DEFERRED, _("Отложено")),
    ]

    case = models.ForeignKey("clients.Case", on_delete=models.PROTECT, related_name="employer_change_candidates")
    current_company = models.ForeignKey(
        "clients.Company", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="employer_change_candidates_as_current",
    )
    source_document = models.ForeignKey(
        "clients.Document", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="employer_change_candidates",
    )
    proposed_name = models.CharField(max_length=255, blank=True, default="")
    proposed_nip = models.CharField(max_length=10, blank=True, default="")
    proposed_regon = models.CharField(max_length=14, blank=True, default="")
    proposed_krs = models.CharField(max_length=10, blank=True, default="")
    effective_from = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=32, blank=True, default="document_ocr")
    confidence = models.CharField(max_length=16, blank=True, default="")
    fingerprint = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    review_note = models.TextField(blank=True, default="")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_employer_changes",
    )
    detected_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-detected_at", "-id"]
        indexes = [models.Index(fields=["case", "status"], name="employer_case_status_idx")]

    @property
    def proposed_label(self) -> str:
        return str(self.proposed_name or (f"NIP {self.proposed_nip}" if self.proposed_nip else _("Не определён")))
