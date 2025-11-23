from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from .constants import DOCUMENT_CHECKLIST, DocumentType


def get_fallback_document_checklist(purpose: str, language: str | None = None):
    checklist_key = (purpose, language)
    if checklist_key in DOCUMENT_CHECKLIST:
        return DOCUMENT_CHECKLIST[checklist_key]

    for (stored_purpose, _lang), documents in DOCUMENT_CHECKLIST.items():
        if stored_purpose == purpose:
            return documents
    return []


class Client(models.Model):
    # --- Списки для выбора ---
    APPLICATION_PURPOSE_CHOICES = [
        ('study', _('Учёба')),
        ('work', _('Работа')),
        ('family', _('Воссоединение семьи')),
    ]
    LANGUAGE_CHOICES = [
        ('pl', _('Польский')),
        ('en', _('Английский')),
        ('ru', _('Русский')),
    ]
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
    phone = models.CharField(max_length=20, verbose_name=_("Телефон"))
    email = models.EmailField(verbose_name="Email", unique=True)
    passport_num = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Номер паспорта"))
    case_number = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("Номер дела"))
    application_purpose = models.CharField(
        max_length=20, choices=APPLICATION_PURPOSE_CHOICES, default='study', verbose_name=_("Цель подачи")
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

    # Последнее состояние дела из inPOL
    inpol_status = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Статус inPOL"))
    inpol_updated_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Дата обновления inPOL"))

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='client_profile',
                                null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_absolute_url(self):
        return reverse('clients:client_detail', kwargs={'pk': self.id})

    def get_document_checklist(self):
        """Возвращает чеклист документов для клиента."""
        # Клиентский портал больше не используется, поэтому ограничение
        # на доступ к чеклисту было снято. Сотрудники видят список всегда.
        required_docs = DocumentRequirement.required_for(self.application_purpose)
        if not required_docs:
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
            documents = docs_map.get(code, [])
            status_list.append({
                'code': code,
                'name': name,
                'is_uploaded': bool(documents),
                'documents': documents
            })
        return status_list

    def get_document_name_by_code(self, doc_code):
        """Возвращает читаемое имя документа по его коду."""
        required_docs = DocumentRequirement.required_for(self.application_purpose)
        if not required_docs:
            required_docs = get_fallback_document_checklist(self.application_purpose, self.language)

        for code, name in required_docs:
            if code == doc_code:
                return name
        return doc_code.replace('_', ' ').capitalize()


class Document(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='documents', verbose_name=_("Клиент"))
    document_type = models.CharField(max_length=100, verbose_name=_("Тип документа"))
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
        if requirement and requirement.custom_name:
            return requirement.custom_name
        if self.document_type in [choice.value for choice in DocumentType]:
            return DocumentType(self.document_type).label
        return self.document_type.replace('_', ' ').capitalize()


class DocumentRequirement(models.Model):
    application_purpose = models.CharField(
        max_length=20,
        choices=Client.APPLICATION_PURPOSE_CHOICES,
        verbose_name=_("Цель подачи"),
    )
    document_type = models.CharField(
        max_length=100,
        verbose_name=_("Код типа документа"),
    )
    custom_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Название документа"))
    position = models.PositiveIntegerField(default=0, verbose_name=_("Порядок отображения"))
    is_required = models.BooleanField(default=True, verbose_name=_("Обязательный документ"))

    class Meta:
        unique_together = ("application_purpose", "document_type")
        ordering = ["position", "id"]
        verbose_name = _("Требование к документу")
        verbose_name_plural = _("Требования к документам")

    def __str__(self):
        return f"{self.get_application_purpose_display()}: {self.custom_name or self.document_type}"

    @classmethod
    def required_for(cls, purpose: str) -> list[tuple[str, str]]:
        records = cls.objects.filter(application_purpose=purpose, is_required=True).order_by("position", "id")
        items: list[tuple[str, str]] = []
        for item in records:
            if item.custom_name:
                items.append((item.document_type, item.custom_name))
                continue
            if item.document_type in [choice.value for choice in DocumentType]:
                items.append((item.document_type, DocumentType(item.document_type).label))
            else:
                items.append((item.document_type, item.document_type.replace('_', ' ').capitalize()))
        return items


class InpolAccount(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Название учётки"))
    base_url = models.URLField(verbose_name=_("Базовый URL inPOL"))
    email = models.EmailField(verbose_name=_("Email для входа"))
    password = models.CharField(max_length=255, verbose_name=_("Пароль для входа"))
    is_active = models.BooleanField(default=True, verbose_name=_("Активный"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        verbose_name = _("Учётная запись inPOL")
        verbose_name_plural = _("Учётные записи inPOL")

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


class InpolProceedingSnapshot(models.Model):
    proceeding_id = models.CharField(max_length=255, unique=True)
    case_number = models.CharField(max_length=255)
    status = models.CharField(max_length=255)
    raw_payload = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "proceeding_id"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.case_number or self.proceeding_id}: {self.status}"

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