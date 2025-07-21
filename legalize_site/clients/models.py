from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from .constants import DOCUMENT_CHECKLIST

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

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='client_profile',
                                null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_absolute_url(self):
        return reverse('clients:client_detail', kwargs={'pk': self.id})

    def get_document_checklist(self):
        """
        Возвращает чеклист, ТОЛЬКО ЕСЛИ у клиента есть доступ.
        """
        if not self.has_checklist_access:
            return []

        checklist_key = (self.application_purpose, self.language)
        required_docs = DOCUMENT_CHECKLIST.get(checklist_key, [])
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
        if not self.has_checklist_access:
            return doc_code.replace('_', ' ').capitalize()

        checklist_key = (self.application_purpose, self.language)
        required_docs = DOCUMENT_CHECKLIST.get(checklist_key, [])
        for code, name in required_docs:
            if code == doc_code:
                return name
        return doc_code.replace('_', ' ').capitalize()


class Document(models.Model):
    DOC_TYPES = [
        ('photos', _('Фотографии')),
        ('payment_confirmation', _('Подтверждение оплаты')),
        ('passport', _('Паспорт')),
        ('enrollment_certificate', _('Справка о зачислении')),
        ('tuition_fee_proof', _('Справка об оплате обучения')),
        ('health_insurance', _('Медицинская страховка')),
        ('address_proof', _('Подтверждение адреса')),
        ('financial_proof', _('Подтверждение финансов')),
        ('załącznik_nr_1', _('Załącznik nr 1')),
        ('starosta_info', _('Informacja starosty')),
        ('employment_contract', _('Трудовой договор')),
        ('pit_proof', _('PIT-37 / Zaświadczenie o niezaleganiu')),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='documents', verbose_name=_("Клиент"))
    document_type = models.CharField(max_length=50, choices=DOC_TYPES, verbose_name=_("Тип документа"))
    file = models.FileField(upload_to='documents/', verbose_name=_("Файл"))
    expiry_date = models.DateField(null=True, blank=True, verbose_name=_("Действителен до"))
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата загрузки"))
    verified = models.BooleanField(default=False, verbose_name=_("Проверено"))

    class Meta:
        verbose_name = _("Документ")
        verbose_name_plural = _("Документы")
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.get_document_type_display()} для {self.client}"


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
        ('work_service', _('Сопровождение (Работа)')),
        ('study_service', _('Сопровождение (Учеба)')),
        ('consultation', _('Консультация')),
        ('document_preparation', _('Подготовка документов')),
        ('full_service', _('Полное сопровождение')),
        ('deposit', _('Задаток')),
        ('other', _('Другое')),
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