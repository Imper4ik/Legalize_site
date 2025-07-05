from django.db import models
from django.urls import reverse


class Client(models.Model):

    LEGAL_BASIS_CHOICES = [
        ('study', 'Учёба'),
        ('work', 'Работа'),
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

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    citizenship = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    passport_num = models.CharField(max_length=50, null=True, blank=True)
    legal_basis = models.CharField(max_length=10, choices=LEGAL_BASIS_CHOICES, default='study')
    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, default='pl')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField(auto_now_add=True)
    legal_basis_end_date = models.DateField(null=True, blank=True, verbose_name="Дата окончания основания")
    apply_for = models.CharField(max_length=100, null=True, blank=True, verbose_name="Кем или для чего подаёт")

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_absolute_url(self):
        return reverse('client_detail', args=[str(self.id)])


class Document(models.Model):
    DOC_TYPES = [
        ('passport', 'Паспорт'),
        ('certificate_enrolment', 'Справка о зачислении'),
        ('certificate_fees', 'Справка об оплате обучения'),
        ('class_schedule', 'Расписание занятий'),
        ('attendance_record', 'Посещаемость'),
        ('transcript_grades', 'Выписка оценок'),
        ('payment_proof', 'Подтверждение оплаты'),
        ('health_insurance', 'Медицинская страховка'),
        ('rental_contract', 'Договор аренды'),
        ('housing_expenses', 'Коммунальные платежи'),
        ('financial_means', 'Документ о средствах'),
        ('other', 'Другое'),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='documents')
    doc_type = models.CharField(max_length=50, choices=DOC_TYPES)
    file = models.FileField(upload_to='documents/')
    is_provided = models.BooleanField(default=False)  # добавлен чекбокс
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_doc_type_display()} для {self.client}"
