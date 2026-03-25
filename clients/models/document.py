import hashlib
from django.db import connection, models
from django.utils import translation
from django.utils.translation import gettext, gettext_lazy as _
from django.conf import settings
from clients.constants import DOCUMENT_CHECKLIST, DocumentType

DOCUMENT_TYPE_VALUES = {choice.value for choice in DocumentType}
DOCUMENT_LABEL_ALIASES: dict[str, list[str]] = {}

def _submission_has_localized_fields() -> bool:
    from django.core.cache import cache
    cached = cache.get("_submission_has_localized_fields")
    if cached is not None:
        return cached
    table_name = "submissions_submission"
    try:
        with connection.cursor() as cursor:
            columns = {
                column.name
                for column in connection.introspection.get_table_description(cursor, table_name)
            }
    except Exception:
        cache.set("_submission_has_localized_fields", False, timeout=60)
        return False
    result = {"name_pl", "name_en", "name_ru"}.issubset(columns)
    cache.set("_submission_has_localized_fields", result, timeout=300)
    return result

def _normalize_document_label(value: str) -> str:
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

def _select_custom_document_name(*, doc_type: str, custom_name: str | None = None, custom_name_pl: str | None = None, custom_name_en: str | None = None, custom_name_ru: str | None = None, language: str | None = None) -> str | None:
    lang = (language or translation.get_language() or "").split("-")[0].lower()
    localized_name = {"pl": custom_name_pl, "en": custom_name_en, "ru": custom_name_ru}.get(lang)
    if localized_name and localized_name.strip():
        return localized_name
    if custom_name and custom_name.strip():
        if doc_type not in DOCUMENT_TYPE_VALUES:
            return custom_name
    return None

def translate_document_name(name: str, language: str | None = None) -> str:
    lang = language or translation.get_language()
    if not lang:
        return str(name)
    with translation.override(lang):
        translated = str(name)
    if not translated or not translated.strip():
        return str(name)
    return translated

def resolve_document_label(doc_type: str, custom_name: str | None = None, custom_name_pl: str | None = None, custom_name_en: str | None = None, custom_name_ru: str | None = None, language: str | None = None) -> str:
    custom_label = _select_custom_document_name(doc_type=doc_type, custom_name=custom_name, custom_name_pl=custom_name_pl, custom_name_en=custom_name_en, custom_name_ru=custom_name_ru, language=language)
    if custom_label:
        return custom_label
    if doc_type in DOCUMENT_TYPE_VALUES:
        return translate_document_name(DocumentType(doc_type).label, language)
    return doc_type.replace('_', ' ').capitalize()

def get_fallback_document_checklist(purpose: str, language: str | None = None):
    checklist_key = (purpose, language)
    if checklist_key in DOCUMENT_CHECKLIST:
        return DOCUMENT_CHECKLIST[checklist_key]
    for (stored_purpose, _lang), documents in DOCUMENT_CHECKLIST.items():
        if stored_purpose == purpose:
            return documents
    return []

def get_available_document_types(purpose: str | None = None) -> set[str]:
    types = set(DOCUMENT_TYPE_VALUES)
    queryset = DocumentRequirement.objects.all()
    if purpose:
        queryset = queryset.filter(application_purpose=purpose)
    types.update(queryset.values_list("document_type", flat=True))
    return types

class Document(models.Model):
    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE, related_name='documents', verbose_name=_("Клиент"))
    document_type = models.CharField(max_length=255, verbose_name=_("Тип документа"))
    file = models.FileField(upload_to='documents/', verbose_name=_("Файл"))
    expiry_date = models.DateField(null=True, blank=True, verbose_name=_("Действителен до"))
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата загрузки"))
    verified = models.BooleanField(default=False, verbose_name=_("Проверено"))
    awaiting_confirmation = models.BooleanField(default=False, verbose_name=_("Ожидает подтверждения"))

    class Meta:
        verbose_name = _("Документ")
        verbose_name_plural = _("Документы")
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.display_name} для {self.client}"

    @property
    def display_name(self) -> str:
        requirement = DocumentRequirement.objects.filter(
            application_purpose=self.client.application_purpose,
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


class DocumentRequirement(models.Model):
    application_purpose = models.CharField(max_length=50, verbose_name=_("Цель подачи"))
    document_type = models.CharField(max_length=255, verbose_name=_("Код типа документа"))
    custom_name = models.CharField(max_length=500, blank=True, null=True, verbose_name=_("Название документа"))
    custom_name_pl = models.CharField(max_length=500, blank=True, null=True, verbose_name=_("Название документа (PL)"))
    custom_name_en = models.CharField(max_length=500, blank=True, null=True, verbose_name=_("Название документа (EN)"))
    custom_name_ru = models.CharField(max_length=500, blank=True, null=True, verbose_name=_("Название документа (RU)"))
    position = models.PositiveIntegerField(default=0, verbose_name=_("Порядок отображения"))
    is_required = models.BooleanField(default=True, verbose_name=_("Обязательный документ"))

    class Meta:
        unique_together = ("application_purpose", "document_type")
        ordering = ["position", "id"]
        verbose_name = _("Требование к документу")
        verbose_name_plural = _("Требования к документам")

    def __str__(self):
        return f"{self.application_purpose}: {self.custom_name or self.document_type}"

    @classmethod
    def catalog_for(cls, purpose: str, language: str | None = None, *, include_optional: bool = True, include_fallback: bool = True) -> list[dict[str, str | bool]]:
        records = list(cls.objects.filter(application_purpose=purpose).order_by("position", "id"))
        items: list[dict[str, str | bool]] = []
        seen: set[str] = set()

        for record in records:
            label = resolve_document_label(
                record.document_type, record.custom_name, record.custom_name_pl,
                record.custom_name_en, record.custom_name_ru, language
            )
            items.append({"code": record.document_type, "label": label, "is_required": record.is_required})
            seen.add(record.document_type)

        if include_fallback:
            fallback = get_fallback_document_checklist(purpose, language)
            for code, _label in fallback:
                if code in seen:
                    continue
                items.append({"code": code, "label": resolve_document_label(code, language=language), "is_required": True})

        if not include_optional:
            items = [item for item in items if item["is_required"]]
        return items

    @classmethod
    def required_for(cls, purpose: str, language: str | None = None) -> list[tuple[str, str]]:
        catalog = cls.catalog_for(purpose, language, include_optional=False, include_fallback=True)
        return [(item["code"], str(item["label"])) for item in catalog]
