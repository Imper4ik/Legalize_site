# clients/models.py

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class Client(models.Model):
    # --- Списки для выбора ---
    APPLICATION_PURPOSE_CHOICES = [
        ('study', 'Учёба'),
        ('work', 'Работа'),
        ('family', 'Воссоединение семьи'),
    ]
    LANGUAGE_CHOICES = [
        ('pl', 'Польский'),
        ('en', 'Английский'),
        ('ru', 'Русский'),
    ]
    STATUS_CHOICES = [
        ('new', 'Новый'),
        ('pending', 'В ожидании'),
        ('approved', 'Одобрен'),
        ('rejected', 'Отклонён'),
    ]

    # --- Поля модели ---
    first_name = models.CharField(max_length=100, verbose_name="Имя")
    last_name = models.CharField(max_length=100, verbose_name="Фамилия")
    citizenship = models.CharField(max_length=100, verbose_name="Гражданство")
    phone = models.CharField(max_length=20, verbose_name="Телефон")
    email = models.EmailField(verbose_name="Email")
    passport_num = models.CharField(max_length=50, null=True, blank=True, verbose_name="Номер паспорта")
    case_number = models.CharField(max_length=100, blank=True, null=True, verbose_name="Номер дела")
    application_purpose = models.CharField(
        max_length=20, choices=APPLICATION_PURPOSE_CHOICES, default='study', verbose_name="Цель подачи"
    )
    basis_of_stay = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="Основание пребывания (виза, TRC и т.д.)"
    )
    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, default='pl', verbose_name="Язык документов")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    legal_basis_end_date = models.DateField(null=True, blank=True, verbose_name="Дата окончания основания")
    submission_date = models.DateField(null=True, blank=True, verbose_name="Дата подачи (Złożone)")
    employer_phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Телефон работодателя")
    fingerprints_date = models.DateField(null=True, blank=True, verbose_name="Дата сдачи отпечатков")
    notes = models.TextField(blank=True, null=True, verbose_name="Uwagi / Заметки")

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_absolute_url(self):
        return reverse('client_detail', args=[str(self.id)])


class Document(models.Model):
    DOC_TYPES = [
        ('passport', 'Паспорт'),
        ('certificate_enrolment', 'Справка о зачислении'),
        ('certificate_fees', 'Справка об оплате обучения'),
        ('health_insurance', 'Медицинская страховка'),
        ('rental_contract', 'Договор аренды'),
        ('financial_means', 'Документ о средствах'),
        ('work_permit', 'Разрешение на работу (Залончник №1)'),
        ('employment_contract', 'Трудовой договор'),
        ('other', 'Другое'),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='documents', verbose_name="Клиент")
    document_type = models.CharField(max_length=50, choices=DOC_TYPES, verbose_name="Тип документа")
    file = models.FileField(upload_to='documents/', verbose_name="Файл")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")

    class Meta:
        verbose_name = _("Документ")
        verbose_name_plural = _("Документы")
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.get_document_type_display()} для {self.client}"


class Payment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Ожидает оплаты'),
        ('partial', 'Частично оплачен'),
        ('paid', 'Оплачен полностью'),
        ('refunded', 'Возврат'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('card', 'Карта'),
        ('cash', 'Наличные'),
        ('transfer', 'Перевод'),
    ]
    SERVICE_CHOICES = [
        ('work_permit', 'Работа'),
        ('student_visa', 'Учёба'),
        ('photo_service', 'Фото'),
        ('consultation', 'Консультация'),
    ]
    SERVICE_PRICES = {
        'work_permit': 1800.00,
        'student_visa': 1400.00,
        'photo_service': 40.00,
        'consultation': 180.00,
    }

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='payments', verbose_name="Клиент")
    service_description = models.CharField(max_length=100, choices=SERVICE_CHOICES, verbose_name="Описание услуги")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Общая сумма")
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Оплаченная сумма")
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending', verbose_name="Статус оплаты")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, blank=True, null=True, verbose_name="Способ оплаты")
    payment_date = models.DateField(blank=True, null=True, verbose_name="Дата оплаты")
    due_date = models.DateField(blank=True, null=True, verbose_name="Оплатить до")
    transaction_id = models.CharField(max_length=255, blank=True, null=True, verbose_name="ID транзакции (если есть)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания счёта")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата последнего обновления")

    def __str__(self):
        return f"Счёт на {self.total_amount} для {self.client}"

    # --- ИСПРАВЛЕНИЕ: ВОТ ЭТИХ МЕТОДОВ НЕ ХВАТАЛО ---
    @property
    def is_fully_paid(self):
        return self.amount_paid >= self.total_amount

    @property
    def amount_due(self):
        return self.total_amount - self.amount_paid


class Reminder(models.Model):
    REMINDER_TYPE_CHOICES = [
        ('payment', 'Оплата'),
        ('document', 'Документ'),
        ('other', 'Другое'),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='reminders', verbose_name="Клиент")
    # НОВОЕ ПОЛЕ: Прямая связь с платежом
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, null=True, blank=True, related_name="reminder")

    reminder_type = models.CharField(max_length=20, choices=REMINDER_TYPE_CHOICES, default='document',
                                     verbose_name="Тип напоминания")
    title = models.CharField(max_length=255, verbose_name="Заголовок напоминания")
    notes = models.TextField(blank=True, null=True, verbose_name="Детали")
    due_date = models.DateField(verbose_name="Ключевая дата")
    is_active = models.BooleanField(default=True, verbose_name="Активно")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Напоминание для {self.client}: {self.title}"

    class Meta:
        ordering = ['due_date']