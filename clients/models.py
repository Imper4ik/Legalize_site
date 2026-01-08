import hashlib

from django.db import models
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext, gettext_lazy as _
from django.conf import settings
from fernet_fields import EncryptedTextField
from .constants import DOCUMENT_CHECKLIST, DocumentType


def _normalize_document_label(value: str) -> str:
    return " ".join(str(value).split()).casefold()


def is_default_document_label(name: str, doc_type: str) -> bool:
    if doc_type not in [choice.value for choice in DocumentType]:
        return False
    normalized = _normalize_document_label(name)
    if not normalized:
        return False

    for language_code, _language_label in settings.LANGUAGES:
        with translation.override(language_code):
            candidate = _normalize_document_label(DocumentType(doc_type).label)
        if candidate == normalized:
            return True
    return False


def _select_custom_document_name(
    *,
    custom_name: str | None = None,
    custom_name_pl: str | None = None,
    custom_name_en: str | None = None,
    custom_name_ru: str | None = None,
    language: str | None = None,
) -> str | None:
    lang = (language or translation.get_language() or "").split("-")[0].lower()
    localized_name = {
        "pl": custom_name_pl,
        "en": custom_name_en,
        "ru": custom_name_ru,
    }.get(lang)
    if localized_name and localized_name.strip():
        return localized_name
    if custom_name and custom_name.strip():
        return custom_name
    return None


def resolve_document_label(
    doc_type: str,
    custom_name: str | None = None,
    custom_name_pl: str | None = None,
    custom_name_en: str | None = None,
    custom_name_ru: str | None = None,
    language: str | None = None,
) -> str:
    resolved_custom_name = _select_custom_document_name(
        custom_name=custom_name,
        custom_name_pl=custom_name_pl,
        custom_name_en=custom_name_en,
        custom_name_ru=custom_name_ru,
        language=language,
    )
    if resolved_custom_name and not is_default_document_label(resolved_custom_name, doc_type):
        return resolved_custom_name
    if doc_type in [choice.value for choice in DocumentType]:
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


def translate_document_name(name: str, language: str | None = None) -> str:
    """Translate a document name for the requested language.

    Some choice labels were stored as lazy translations, but depending on the
    active language when they were created, they could render in the fallback
    language. Applying an explicit override ensures we always return the
    correct translation for the interface language selected by the user.
    """

    lang = language or translation.get_language()
    if not lang:
        return gettext(name)

    with translation.override(lang):
        translated = gettext(name)

    if not translated or not str(translated).strip():
        return str(name)
    return translated


class Client(models.Model):
    # --- Списки для выбора ---
    APPLICATION_PURPOSE_CHOICES = [
        ('study', _('Учёба')),
        ('work', _('Работа')),
        ('family', _('Воссоединение семьи')),
    ]
    LANGUAGE_CHOICES = getattr(settings, "LANGUAGES", [
        ('pl', _('Польский')),
        ('en', _('Английский')),
        ('ru', _('Русский')),
    ])
    STATUS_CHOICES = [
        ('new', _('Новый')),
        ('pending', _('В ожидании')),
        ('approved', _('Одобрен')),
        ('rejected', _('Отклонён')),
    ]

    # --- Поля модели ---
    first_name = models.CharField(max_length=100, verbose_name=_("Имя"))
    last_name = models.CharField(max_length=100, verbose_name=_("Фамилия"))
    citizenship = models.CharField(max_length=100, verbose_name=_("Гражданство"))
    birth_date = models.DateField(null=True, blank=True, verbose_name=_("Дата рождения"))
    phone = models.CharField(max_length=20, verbose_name=_("Телефон"))
    email = models.EmailField(verbose_name="Email", unique=True)
    passport_num = EncryptedTextField(null=True, blank=True, verbose_name=_("Номер паспорта"))
    case_number = EncryptedTextField(blank=True, null=True, verbose_name=_("Номер дела"))
    case_number_hash = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    application_purpose = models.CharField(
        max_length=64,
        default='study',
        verbose_name=_("Цель подачи"),
    )
    basis_of_stay = models.CharField(
        max_length=100, blank=True, null=True, verbose_name=_("Основание пребывания (виза, TRC и т.д.)")
    )
    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, default='pl', verbose_name=_("Язык документов"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', verbose_name=_("Статус"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))
    legal_basis_end_date = models.DateField(null=True, blank=True, verbose_name=_("Дата окончания основания"))
    submission_date = models.DateField(null=True, blank=True, verbose_name=_("Дата подачи (Złożone)"))
    employer_phone = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("Телефон работодателя"))
    fingerprints_date = models.DateField(null=True, blank=True, verbose_name=_("Дата сдачи отпечатков"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("Uwagi / Заметки"))
    has_checklist_access = models.BooleanField(default=False, verbose_name=_("Доступ к чеклисту предоставлен"))

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='client_profile',
                                null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @staticmethod
    def normalize_case_number(case_number: str) -> str:
        return case_number.strip().upper().replace(" ", "")

    @classmethod
    def hash_case_number(cls, case_number: str) -> str:
        normalized = cls.normalize_case_number(case_number)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def save(self, *args, **kwargs):
        if self.case_number:
            self.case_number_hash = self.hash_case_number(self.case_number)
        else:
            self.case_number_hash = None

        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "case_number" in update_fields:
            update_fields = set(update_fields)
            update_fields.add("case_number_hash")
            kwargs["update_fields"] = list(update_fields)

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('clients:client_detail', kwargs={'pk': self.id})

    def get_application_purpose_display(self):
        from submissions.models import Submission

        if self.application_purpose:
            submission_name = Submission.objects.filter(
                slug=self.application_purpose
            ).values_list('name', flat=True).first()
            if submission_name:
                return submission_name

        return dict(self.APPLICATION_PURPOSE_CHOICES).get(
            self.application_purpose, self.application_purpose or ''
        )

    def get_document_checklist(self):
        """Возвращает чеклист документов для клиента."""
        # Клиентский портал больше не используется, поэтому ограничение
        # на доступ к чеклисту было снято. Сотрудники видят список всегда.
        current_language = translation.get_language() or self.language
        required_docs = DocumentRequirement.required_for(self.application_purpose, current_language)
        has_custom_checklist = DocumentRequirement.objects.filter(
            application_purpose=self.application_purpose
        ).exists()

        if not required_docs and not has_custom_checklist:
            required_docs = get_fallback_document_checklist(self.application_purpose, self.language)
        if not required_docs:
            return []

        uploaded_docs = self.documents.all().order_by('-uploaded_at')

        docs_map = {}
        for doc in uploaded_docs:
            if doc.document_type not in docs_map:
                docs_map[doc.document_type] = []
            docs_map[doc.document_type].append(doc)

        status_list = []
        for code, name in required_docs:
            translated_name = translate_document_name(name, current_language)
            documents = docs_map.get(code, [])
            status_list.append({
                'code': code,
                'name': translated_name,
                'is_uploaded': bool(documents),
                'documents': documents
            })
        return status_list

    def get_document_name_by_code(self, doc_code):
        """Возвращает читаемое имя документа по его коду."""
        current_language = translation.get_language() or self.language
        required_docs = DocumentRequirement.required_for(self.application_purpose, current_language)
        if not required_docs:
            required_docs = get_fallback_document_checklist(self.application_purpose, self.language)

        for code, name in required_docs:
            if code == doc_code:
                return translate_document_name(name, current_language)
        return doc_code.replace('_', ' ').capitalize()


class Document(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='documents', verbose_name=_("Клиент"))
    document_type = models.CharField(max_length=255, verbose_name=_("Тип документа"))
    file = models.FileField(upload_to='documents/', verbose_name=_("Файл"))
    expiry_date = models.DateField(null=True, blank=True, verbose_name=_("Действителен до"))
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата загрузки"))
    verified = models.BooleanField(default=False, verbose_name=_("Проверено"))

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
        """Возвращает True, если документ относится к стандартным типам чеклиста."""

        return self.document_type in [choice.value for choice in DocumentType]


class DocumentRequirement(models.Model):
    application_purpose = models.CharField(
        max_length=50,
        verbose_name=_("Цель подачи"),
    )
    document_type = models.CharField(
        max_length=255,
        verbose_name=_("Код типа документа"),
    )
    custom_name = models.CharField(max_length=500, blank=True, null=True, verbose_name=_("Название документа"))
    custom_name_pl = models.CharField(
        max_length=500, blank=True, null=True, verbose_name=_("Название документа (PL)")
    )
    custom_name_en = models.CharField(
        max_length=500, blank=True, null=True, verbose_name=_("Название документа (EN)")
    )
    custom_name_ru = models.CharField(
        max_length=500, blank=True, null=True, verbose_name=_("Название документа (RU)")
    )
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
    def required_for(cls, purpose: str, language: str | None = None) -> list[tuple[str, str]]:
        records = cls.objects.filter(application_purpose=purpose, is_required=True).order_by("position", "id")
        items: list[tuple[str, str]] = []
        for item in records:
            label = resolve_document_label(
                item.document_type,
                item.custom_name,
                item.custom_name_pl,
                item.custom_name_en,
                item.custom_name_ru,
                language,
            )
            items.append((item.document_type, label))
        return items


class Payment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', _('Ожидает оплаты')),
        ('partial', _('Частично оплачен')),
        ('paid', _('Оплачен полностью')),
        ('refunded', _('Возврат')),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('card', _('Карта')),
        ('cash', _('Наличные')),
        ('transfer', _('Перевод')),
    ]
    SERVICE_CHOICES = [
        ('work_service', _('Работа')),
        ('study_service', _('Учеба')),
        ('consultation', _('Консультация')),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='payments', verbose_name=_("Клиент"))
    service_description = models.CharField(max_length=100, choices=SERVICE_CHOICES, verbose_name=_("Описание услуги"))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Общая сумма"))
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_("Оплаченная сумма"))
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending',
                              verbose_name=_("Статус оплаты"))
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, blank=True, null=True,
                                      verbose_name=_("Способ оплаты"))
    payment_date = models.DateField(blank=True, null=True, verbose_name=_("Дата оплаты"))
    due_date = models.DateField(blank=True, null=True, verbose_name=_("Оплатить до"))
    transaction_id = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("ID транзакции (если есть)"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания счёта"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Дата последнего обновления"))

    def __str__(self):
        return f"Счёт на {self.total_amount} для {self.client}"

    @property
    def is_fully_paid(self):
        return self.amount_paid >= self.total_amount

    @property
    def amount_due(self):
        return self.total_amount - self.amount_paid


class Reminder(models.Model):
    REMINDER_TYPE_CHOICES = [
        ('payment', _('Оплата')),
        ('document', _('Документ')),
        ('other', _('Другое')),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='reminders', verbose_name=_("Клиент"))
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, null=True, blank=True, related_name="reminder")
    document = models.OneToOneField(Document, on_delete=models.CASCADE, null=True, blank=True, related_name="reminder")
    reminder_type = models.CharField(max_length=20, choices=REMINDER_TYPE_CHOICES, default='document',
                                     verbose_name=_("Тип напоминания"))
    title = models.CharField(max_length=255, verbose_name=_("Заголовок напоминания"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("Детали"))
    due_date = models.DateField(verbose_name=_("Ключевая дата"))
    is_active = models.BooleanField(default=True, verbose_name=_("Активно"))
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Напоминание для {self.client}: {self.title}"

    class Meta:
        ordering = ['due_date']
