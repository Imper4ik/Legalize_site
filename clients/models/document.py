from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, cast, TYPE_CHECKING
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from clients.constants import DOCUMENT_CHECKLIST, DocumentType
from clients.validators import validate_uploaded_document
from legalize_site.soft_delete import SoftDeleteModel

if TYPE_CHECKING:
    pass


DOCUMENT_TYPE_VALUES = {choice.value for choice in DocumentType}
DOCUMENT_LABEL_ALIASES: dict[str, list[str]] = {}
PARSED_DATA_PII_KEYS = {"full_name", "first_name", "last_name", "case_number", "text", "raw_text"}
PARSED_DATA_RAW_TEXT_KEYS = {"text", "raw_text"}


def document_upload_path(_instance: Document, filename: str) -> str:
    """Store uploaded documents without preserving user-provided filenames."""

    suffix = Path(filename or "").suffix.lower() or ".bin"
    return f"documents/{uuid4().hex}{suffix}"


def _normalize_document_label(value: Any) -> str:
    return " ".join(str(value).split()).casefold()


def _document_label_variants(doc_type: str) -> set[str]:
    if doc_type not in DOCUMENT_TYPE_VALUES:
        return set()
    variants = set()
    language_codes = {code for code, _language_label in settings.LANGUAGES}
    language_codes.add("ru")
    for language_code in language_codes:
        with translation.override(language_code):
            variants.add(_normalize_document_label(DocumentType(doc_type).label))
    for alias in DOCUMENT_LABEL_ALIASES.get(doc_type, []):
        variants.add(_normalize_document_label(alias))
    return {variant for variant in variants if variant}


def is_default_document_label(name: str, doc_type: str) -> bool:
    if doc_type not in DOCUMENT_TYPE_VALUES:
        return False
    normalized = _normalize_document_label(name)
    if not normalized:
        return False
    return normalized in _document_label_variants(doc_type)


def _fallback_document_label_for_code(doc_type: str, language: str | None = None) -> str | None:
    for (_purpose, _language_code), documents in DOCUMENT_CHECKLIST.items():
        for code, label in documents:
            if code == doc_type:
                return translate_document_name(label, language)
    return None


def _is_fallback_document_label(value: str, doc_type: str) -> bool:
    normalized = _normalize_document_label(value)
    if not normalized:
        return False
    languages = {code for code, _label in settings.LANGUAGES}
    languages.update({"pl", "en", "ru"})
    return any(
        normalized == _normalize_document_label(label)
        for language_code in languages
        for label in [_fallback_document_label_for_code(doc_type, language_code)]
        if label
    )


def _select_custom_document_name(*, doc_type: str, custom_name: str | None = None, custom_name_pl: str | None = None, custom_name_en: str | None = None, custom_name_ru: str | None = None, language: str | None = None) -> str | None:
    lang = (language or translation.get_language() or "").split("-")[0].lower()
    localized_name = {"pl": custom_name_pl, "en": custom_name_en, "ru": custom_name_ru}.get(lang)
    if localized_name and localized_name.strip():
        return localized_name
    if custom_name and custom_name.strip():
        if doc_type not in DOCUMENT_TYPE_VALUES and not _is_fallback_document_label(custom_name, doc_type):
            return custom_name
    return None


def translate_document_name(name: Any, language: str | None = None) -> str:
    source = str(getattr(name, "_args", [name])[0])
    lang = language or translation.get_language()
    if not lang:
        return source
    with translation.override(lang):
        translated = str(name)
    if not translated or not translated.strip():
        return source
    return translated


def _first_day_of_month(value: date | None) -> date | None:
    if value is None:
        return None
    return value.replace(day=1)


def resolve_document_label(doc_type: str, custom_name: str | None = None, custom_name_pl: str | None = None, custom_name_en: str | None = None, custom_name_ru: str | None = None, language: str | None = None) -> str:
    custom_label = _select_custom_document_name(doc_type=doc_type, custom_name=custom_name, custom_name_pl=custom_name_pl, custom_name_en=custom_name_en, custom_name_ru=custom_name_ru, language=language)
    if custom_label:
        return custom_label
    if doc_type in DOCUMENT_TYPE_VALUES:
        return translate_document_name(DocumentType(doc_type).label, language)
    fallback_label = _fallback_document_label_for_code(doc_type, language)
    if fallback_label:
        return fallback_label
    return doc_type.replace('_', ' ').capitalize()


def get_fallback_document_checklist(purpose: str, language: str | None = None) -> list[tuple[str, Any]]:
    checklist_key = (purpose, language)
    if checklist_key in DOCUMENT_CHECKLIST:
        return cast(list[tuple[str, Any]], DOCUMENT_CHECKLIST[checklist_key])
    for (stored_purpose, _lang), documents in DOCUMENT_CHECKLIST.items():
        if stored_purpose == purpose:
            return cast(list[tuple[str, Any]], documents)
    return []


def get_available_document_types(purpose: str | None = None) -> set[str]:
    types = set(DOCUMENT_TYPE_VALUES)
    queryset = DocumentRequirement.objects.all()
    if purpose:
        queryset = queryset.filter(application_purpose=purpose)
    types.update(queryset.values_list("document_type", flat=True))
    return types


class Document(SoftDeleteModel):
    OCR_STATUS_CHOICES = [
        ("skipped", _("Пропущено")),
        ("success", _("Успешно")),
        ("failed", _("Ошибка")),
        ("pending", _("Ожидает")),
    ]

    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE, related_name='documents', verbose_name=_("Клиент"))
    document_type = models.CharField(max_length=255, verbose_name=_("Тип документа"))
    file = models.FileField(upload_to=document_upload_path, verbose_name=_("Файл"), validators=[validate_uploaded_document])
    expiry_date = models.DateField(null=True, blank=True, verbose_name=_("Действителен до"))
    zus_period_month = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("ZUS RCA — месяц"),
        help_text=_("Первый день месяца, за который загружен ZUS RCA."),
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата загрузки"))
    verified = models.BooleanField(default=False, verbose_name=_("Проверено"))
    awaiting_confirmation = models.BooleanField(default=False, verbose_name=_("Ожидает подтверждения"))

    ocr_status = models.CharField(
        max_length=20,
        choices=OCR_STATUS_CHOICES,
        default="skipped",
        verbose_name=_("Статус OCR"),
    )
    ocr_name_mismatch = models.BooleanField(
        default=False,
        verbose_name=_("Несовпадение имени OCR"),
    )
    parsed_data: models.JSONField[dict[str, Any]] = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_("Распознанные данные"),
    )

    if TYPE_CHECKING:
        _preloaded_version_count: int
        _preloaded_requirement: DocumentRequirement | None
        file_exists: bool

    class Meta:
        verbose_name = _("Документ")
        verbose_name_plural = _("Документы")
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=["client", "document_type"], name="doc_client_type_idx"),
            models.Index(fields=["ocr_status", "awaiting_confirmation"], name="doc_ocr_confirm_idx"),
            models.Index(fields=["client", "document_type", "zus_period_month"], name="doc_zus_period_idx"),
            models.Index(
                fields=["expiry_date"],
                name="doc_expiry_date_idx",
                condition=models.Q(expiry_date__isnull=False),
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "document_type", "zus_period_month"],
                condition=models.Q(
                    document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
                    zus_period_month__isnull=False,
                    archived_at__isnull=True,
                ),
                name="unique_zus_rca_period_per_client",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} для {self.client}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.document_type == DocumentType.ZUS_RCA_OR_INSURANCE.value:
            self.zus_period_month = _first_day_of_month(self.zus_period_month)
        else:
            self.zus_period_month = None
        super().save(*args, **kwargs)

    @property
    def display_name(self) -> str:
        if hasattr(self, "_preloaded_requirement"):
            requirement = self._preloaded_requirement
        else:
            purpose = self.client.get_document_requirement_purpose()
            requirement = DocumentRequirement.objects.filter(
                application_purpose=purpose,
                document_type=self.document_type,
            ).first()
        if requirement:
            return resolve_document_label(
                requirement.document_type,
                requirement.custom_name,
                requirement.custom_name_pl,
                requirement.custom_name_en,
                requirement.custom_name_ru,
                translation.get_language() or self.client.language,
            )
        return resolve_document_label(
            self.document_type,
            language=translation.get_language() or self.client.language,
        )

    @property
    def is_standard_type(self) -> bool:
        return self.document_type in DOCUMENT_TYPE_VALUES

    @property
    def version_count(self) -> int:
        if hasattr(self, "_preloaded_version_count"):
            return self._preloaded_version_count
        return self.versions.count()

    @property
    def ocr_status_badge(self) -> str:
        badge_map = {
            "skipped": "",
            "success": "bg-success",
            "failed": "bg-danger",
            "pending": "bg-warning text-dark",
        }
        return badge_map.get(self.ocr_status, "")

    def scrub_parsed_pii(self) -> bool:
        """Remove PII and raw text from parsed_data, keeping only metadata."""
        if not self.parsed_data:
            return False

        scrubbed = False
        removed_raw_text = False
        for key in PARSED_DATA_PII_KEYS:
            if key in self.parsed_data:
                del self.parsed_data[key]
                scrubbed = True
                removed_raw_text = removed_raw_text or key in PARSED_DATA_RAW_TEXT_KEYS

        self.parsed_data["pii_scrubbed"] = True
        if removed_raw_text:
            self.parsed_data["raw_text_removed"] = True
        return scrubbed


class DocumentRequirement(models.Model):
    application_purpose = models.CharField(max_length=20, verbose_name=_("Цель подачи"))
    document_type = models.CharField(max_length=255, verbose_name=_("Тип документа"))
    custom_name = models.CharField(max_length=255, blank=True, verbose_name=_("Название"))
    custom_name_pl = models.CharField(max_length=255, blank=True, verbose_name=_("Название (PL)"))
    custom_name_en = models.CharField(max_length=255, blank=True, verbose_name=_("Название (EN)"))
    custom_name_ru = models.CharField(max_length=255, blank=True, verbose_name=_("Название (RU)"))
    is_required = models.BooleanField(default=True, verbose_name=_("Обязательный документ"))
    position = models.PositiveIntegerField(default=0, verbose_name=_("Порядок отображения"))

    class Meta:
        ordering = ["position", "id"]
        unique_together = (("application_purpose", "document_type"),)
        verbose_name = _("Требование к документу")
        verbose_name_plural = _("Требования к документам")
