# portal/models.py
from django.db import models
from django.contrib.auth.models import User


# Модель для хранения данных из клиентской анкеты
class ClientApplication(models.Model):
    # Привязка к пользователю, который заполнил анкету
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='application')

    # Шаг 1: Цель пребывания
    PURPOSE_CHOICES = [
        ('учеба', 'Учеба в университете/школе'),
        ('работа', 'Работа'),
        ('воссоединение', 'Воссоединение с семьей'),
        ('другое', 'Другое'),
    ]
    purpose_of_stay = models.CharField(max_length=50, choices=PURPOSE_CHOICES, verbose_name="Основная цель пребывания")
    purpose_other = models.CharField(max_length=255, blank=True, null=True, verbose_name="Другая цель (укажите)")

    # Шаг 2: Личные данные
    surname_latin = models.CharField(max_length=100, verbose_name="Фамилия (латиницей)")
    name_latin = models.CharField(max_length=100, verbose_name="Имя (имена) (латиницей)")
    previous_name_surname = models.CharField(max_length=200, blank=True, null=True,
                                             verbose_name="Предыдущие имя и фамилия")
    family_name = models.CharField(max_length=100, verbose_name="Родовая фамилия")
    father_name = models.CharField(max_length=100, verbose_name="Имя отца")
    mother_name = models.CharField(max_length=100, verbose_name="Имя матери")
    mother_maiden_name = models.CharField(max_length=100, verbose_name="Девичья фамилия матери")
    date_of_birth = models.DateField(verbose_name="Дата рождения")
    sex = models.CharField(max_length=10, choices=[('мужской', 'Мужской'), ('женский', 'Женский')], verbose_name="Пол")
    place_of_birth = models.CharField(max_length=100, verbose_name="Место рождения (город)")
    country_of_birth = models.CharField(max_length=100, verbose_name="Страна рождения")
    citizenship = models.CharField(max_length=100, verbose_name="Гражданство")
    nationality = models.CharField(max_length=100, verbose_name="Национальность")
    marital_status = models.CharField(max_length=50, verbose_name="Семейное положение")
    education = models.CharField(max_length=100, verbose_name="Образование")
    pesel = models.CharField(max_length=11, blank=True, null=True, verbose_name="Номер PESEL (если есть)")
    height = models.PositiveIntegerField(verbose_name="Рост (в см)")
    eye_color = models.CharField(max_length=50, verbose_name="Цвет глаз")

    # Шаг 3: Контакты и адрес
    phone_number = models.CharField(max_length=20, verbose_name="Контактный телефон (польский)")
    voivodeship = models.CharField(max_length=100, verbose_name="Воеводство")
    city = models.CharField(max_length=100, verbose_name="Город/Населенный пункт")
    street = models.CharField(max_length=100, verbose_name="Улица")
    house_number = models.CharField(max_length=10, verbose_name="Номер дома")
    apartment_number = models.CharField(max_length=10, blank=True, null=True, verbose_name="Номер квартиры")
    postal_code = models.CharField(max_length=10, verbose_name="Почтовый индекс")

    # Шаг 4: Информация о пребывании и финансах
    last_entry_date = models.DateField(verbose_name="Дата последнего въезда в Польшу")
    legal_basis_of_stay = models.CharField(max_length=50,
                                           choices=[('виза', 'Виза'), ('безвиз', 'Безвиз'), ('карта', 'Карта побыту')],
                                           verbose_name="Основание для текущего пребывания")
    source_of_funds = models.CharField(max_length=100, blank=True, null=True,
                                       verbose_name="Источник средств к существованию (для учебы)")

    # Шаг 5: Загрузка документов
    photo = models.FileField(upload_to='client_documents/', verbose_name="Фотография")
    passport_scan = models.FileField(upload_to='client_documents/', verbose_name="Скан паспорта")
    rental_agreement = models.FileField(upload_to='client_documents/', verbose_name="Договор аренды")
    health_insurance = models.FileField(upload_to='client_documents/', verbose_name="Медицинская страховка")

    # Документы, зависящие от цели
    proof_of_study = models.FileField(upload_to='client_documents/', blank=True, null=True,
                                      verbose_name="Справка из учебного заведения")
    proof_of_funds = models.FileField(upload_to='client_documents/', blank=True, null=True,
                                      verbose_name="Подтверждение наличия средств")
    work_attachment_1 = models.FileField(upload_to='client_documents/', blank=True, null=True,
                                         verbose_name="Załącznik nr 1 (от работодателя)")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Заявка от {self.surname_latin} {self.name_latin}"