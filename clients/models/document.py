from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, cast
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from clients.constants import DOCUMENT_CHECKLIST, DocumentType
from clients.models.consistency import assert_case_client_consistent
from clients.validators import validate_uploaded_document
from fernet_fields import EncryptedJSONField
from legalize_site.soft_delete import SoftDeleteModel, SoftDeleteQuerySet

logger = logging.getLogger(__name__)

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
    if language is not None:
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


class DocumentQuerySet(SoftDeleteQuerySet):
    def for_active_cases(self) -> Self:
        return self.filter(case__isnull=False, case__archived_at__isnull=True)


class DocumentManager(models.Manager.from_queryset(DocumentQuerySet)):  # type: ignore[misc]
    def get_queryset(self) -> DocumentQuerySet:
        return super().get_queryset().active()


class Document(SoftDeleteModel):
    objects = DocumentManager()  # type: ignore[misc]
    all_objects = DocumentQuerySet.as_manager()  # type: ignore[misc]

    OCR_STATUS_CHOICES = [
        ("skipped", _("Пропущено")),
        ("success", _("Успешно")),
        ("failed", _("Ошибка")),
        ("pending", _("Ожидает")),
    ]

    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE, related_name='documents', verbose_name=_("Клиент"))
    case = models.ForeignKey(
        'clients.Case',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='documents',
        verbose_name=_("Дело"),
    )
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
    rejection_reason = models.TextField(blank=True, null=True, verbose_name=_("Причина отклонения"))

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
    parsed_data: EncryptedJSONField = EncryptedJSONField(
        null=True,
        blank=True,
        verbose_name=_("Распознанные данные"),
    )

    version = models.PositiveIntegerField(default=1, verbose_name=_("Версия"))
    metadata_version = models.PositiveIntegerField(default=1, verbose_name=_("Версия метаданных"))
    ocr_version = models.PositiveIntegerField(default=1, verbose_name=_("Версия OCR"))
    copied_from_document = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="copies",
        verbose_name=_("Скопировано из документа"),
    )
    confirms_submission = models.ForeignKey(
        "clients.WniosekSubmission",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proof_documents",
        verbose_name=_("Подтверждает подачу"),
        help_text=_("Подача (wniosek), позиции которой закрывает этот штамп/подтверждение подачи."),
    )
    is_test_data = models.BooleanField(default=False, db_index=True)
    is_demo_data = models.BooleanField(default=False, db_index=True)

    if TYPE_CHECKING:
        _preloaded_version_count: int
        _preloaded_requirement: DocumentRequirement | None
        file_exists: bool

    class Meta:
        verbose_name = _("Документ")
        verbose_name_plural = _("Документы")
        ordering = ['-uploaded_at']
        base_manager_name = "all_objects"
        indexes = [
            models.Index(fields=["client", "document_type"], name="doc_client_type_idx"),
            models.Index(fields=["case", "document_type"], name="doc_case_type_idx"),
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
                fields=["case", "document_type", "zus_period_month"],
                condition=models.Q(
                    case__isnull=False,
                    document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
                    zus_period_month__isnull=False,
                    archived_at__isnull=True,
                ),
                name="unique_zus_rca_period_per_case",
            ),
        ]

    def __str__(self) -> str:
        from django.utils.translation import gettext
        return f"{self.display_name} {gettext('for')} {self.client}"

    def clean(self) -> None:
        super().clean()
        if self.case_id is None:
            if self.client_id:
                from clients.models.consistency import resolve_required_case
                try:
                    self.case = resolve_required_case(self.client_id, self.__class__.__name__)
                except ValidationError as e:
                    raise ValidationError(e.message)
            else:
                raise ValidationError("Case is required.")
        if self.case_id and self.client_id and self.case and self.case.client_id != self.client_id:
            raise ValidationError("Клиент и дело не согласованы.")

    def save(self, *args: Any, **kwargs: Any) -> None:
        update_fields = kwargs.get("update_fields")
        if self.case_id is None and self.client_id:
            from clients.models.consistency import resolve_required_case
            self.case = resolve_required_case(self.client_id, self.__class__.__name__)
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("case")
                kwargs["update_fields"] = list(update_fields)
        if self.document_type == DocumentType.ZUS_RCA_OR_INSURANCE.value:
            self.zus_period_month = _first_day_of_month(self.zus_period_month)
        else:
            self.zus_period_month = None
        assert_case_client_consistent(self)
        super().save(*args, **kwargs)

    def on_archive(self) -> None:
        from clients.models.client import Client
        from clients.services.onboarding_purposes import clear_onboarding_notifications_cache
        if self.client_id:
            try:
                client = Client.all_objects.filter(pk=self.client_id).first()
                if client:
                    clear_onboarding_notifications_cache(client)
            except Exception:
                logger.warning("Failed to clear onboarding notifications cache on document archive")

    def on_restore(self) -> None:
        from clients.models.client import Client
        from clients.services.onboarding_purposes import clear_onboarding_notifications_cache
        if self.client_id:
            try:
                client = Client.all_objects.filter(pk=self.client_id).first()
                if client:
                    clear_onboarding_notifications_cache(client)
            except Exception:
                logger.warning("Failed to clear onboarding notifications cache on document restore")

    @property
    def display_name(self) -> str:
        if hasattr(self, "_preloaded_requirement"):
            requirement = self._preloaded_requirement
        else:
            requirement = self._requirement_for_display()
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

    def _requirement_for_display(self) -> DocumentRequirement | None:
        """Resolve this document's DocumentRequirement, caching by purpose.

        Without ``_preloaded_requirement`` (set by the checklist builder) every
        ``display_name`` access used to issue its own query, an N+1 when rendering
        document lists. The requirement only depends on (purpose, document_type),
        so the full purpose→{type: requirement} map is built once and cached on
        the shared client instance, making subsequent lookups query-free.
        """
        purpose = self.client.get_document_requirement_purpose()
        cache: dict[str, dict[str, DocumentRequirement]] | None = getattr(
            self.client, "_document_requirement_map_cache", None
        )
        if cache is None:
            cache = {}
            setattr(self.client, "_document_requirement_map_cache", cache)
        requirement_map = cache.get(purpose)
        if requirement_map is None:
            requirement_map = {
                requirement.document_type: requirement
                for requirement in DocumentRequirement.objects.filter(application_purpose=purpose)
            }
            cache[purpose] = requirement_map
        return requirement_map.get(self.document_type)

    @property
    def computed_status(self) -> str:
        from django.utils import timezone
        today = timezone.localdate()
        if self.archived_at is not None:
            return "archived"
        if self.expiry_date is not None and self.expiry_date < today:
            return "expired"
        if self.rejection_reason:
            return "rejected"
        if self.verified:
            return "approved"
        return "pending_review"

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

        if "employer_nip" in self.parsed_data:
            val = str(self.parsed_data["employer_nip"])
            if val:
                val_clean = "".join(c for c in val if c.isdigit())
                if len(val_clean) > 4:
                    self.parsed_data["employer_nip"] = val_clean[:2] + "*" * (len(val_clean) - 4) + val_clean[-2:]
                else:
                    self.parsed_data["employer_nip"] = "***"
                scrubbed = True

        if "detected_names" in self.parsed_data:
            self.parsed_data["detected_names"] = []
            scrubbed = True

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
    sample_image = models.ImageField(
        upload_to="document_samples/",
        null=True,
        blank=True,
        verbose_name=_("Образец документа"),
    )

    class Meta:
        ordering = ["position", "id"]
        unique_together = (("application_purpose", "document_type"),)
        verbose_name = _("Требование к документу")
        verbose_name_plural = _("Требования к документам")

    def __str__(self) -> str:
        return f"{self.application_purpose}: {self.custom_name or self.document_type}"

    @classmethod
    def catalog_for(
        cls,
        purpose: str,
        language: str | None = None,
        *,
        include_optional: bool = True,
        include_fallback: bool = True,
    ) -> list[dict[str, Any]]:
        records = list(cls.objects.filter(application_purpose=purpose).order_by("position", "id"))
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for record in records:
            label = resolve_document_label(
                record.document_type,
                record.custom_name,
                record.custom_name_pl,
                record.custom_name_en,
                record.custom_name_ru,
                language,
            )
            items.append({
                "code": record.document_type,
                "label": label,
                "is_required": record.is_required,
                "sample_image_url": record.sample_image.url if record.sample_image else None,
            })
            seen.add(record.document_type)

        if include_fallback:
            fallback = get_fallback_document_checklist(purpose, language)
            for code, _label in fallback:
                if code in seen:
                    continue
                items.append({
                    "code": code,
                    "label": resolve_document_label(code, language=language),
                    "is_required": True,
                })

        if not include_optional:
            items = [item for item in items if item["is_required"]]
        return items

    @classmethod
    def required_for(cls, purpose: str, language: str | None = None) -> list[tuple[str, str]]:
        catalog = cls.catalog_for(purpose, language, include_optional=False, include_fallback=True)
        return [(item["code"], str(item["label"])) for item in catalog]


class ClientDocumentRequirement(models.Model):
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, related_name="custom_document_requirements")
    case = models.ForeignKey(
        "clients.Case",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="custom_document_requirements",
    )
    document_type = models.CharField(max_length=255, blank=True, default="")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    is_required = models.BooleanField(default=True)
    due_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_client_document_requirements",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["due_date", "created_at"]
        indexes = [
            models.Index(fields=["client", "is_active"], name="cl_doc_req_cl_act_idx"),
            models.Index(fields=["case", "is_active"], name="cl_doc_req_case_act_idx"),
            models.Index(fields=["document_type"], name="cl_doc_req_type_idx"),
            models.Index(fields=["due_date"], name="cl_doc_req_due_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.case_id is None:
            if self.client_id:
                from clients.models.consistency import resolve_required_case
                try:
                    self.case = resolve_required_case(self.client_id, self.__class__.__name__)
                except ValidationError as e:
                    raise ValidationError(e.message)
            else:
                raise ValidationError("Case is required.")
        if self.case_id and self.client_id and self.case and self.case.client_id != self.client_id:
            raise ValidationError("Клиент и дело не согласованы.")

    def save(self, *args: Any, **kwargs: Any) -> None:
        update_fields = kwargs.get("update_fields")
        if self.case_id is None and self.client_id:
            from clients.models.consistency import resolve_required_case
            self.case = resolve_required_case(self.client_id, self.__class__.__name__)
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("case")
                kwargs["update_fields"] = list(update_fields)
        assert_case_client_consistent(self)
        super().save(*args, **kwargs)
        if not self.document_type and self.pk:
            self.document_type = f"client_custom_{self.pk}"
            super().save(update_fields=["document_type"])
