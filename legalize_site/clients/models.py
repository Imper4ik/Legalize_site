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

    # Новые поля для динамических чеклистов
    application_purpose = models.CharField(
        max_length=20,
        choices=APPLICATION_PURPOSE_CHOICES,
        default='study',
        verbose_name="Цель подачи"
    )
    basis_of_stay = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Основание пребывания (виза, TRC и т.д.)"
    )
    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, default='pl', verbose_name="Язык документов")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    legal_basis_end_date = models.DateField(null=True, blank=True, verbose_name="Дата окончания основания")

    notes = models.TextField(blank=True, null=True, verbose_name="Uwagi / Заметки")

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_absolute_url(self):
        return reverse('client_detail', args=[str(self.id)])


class Document(models.Model):
    # Этот список определяет ВСЕ возможные типы документов,
    # которые в принципе можно загрузить в систему.
    DOC_TYPES = [
        # Для учёбы
        ('passport', 'Паспорт'),
        ('certificate_enrolment', 'Справка о зачислении'),
        ('certificate_fees', 'Справка об оплате обучения'),
        ('health_insurance', 'Медицинская страховка'),
        ('rental_contract', 'Договор аренды'),
        ('financial_means', 'Документ о средствах'),

        # Для работы
        ('work_permit', 'Разрешение на работу (Залончник №1)'),
        ('employment_contract', 'Трудовой договор'),

        # Общие/Другие
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