"""
ClientBuilder - Паттерн Builder для создания клиентов.

Использование:
    client = (
        ClientBuilder()
        .with_basic_info("Иван", "Петров", "ivan@example.com")
        .with_contact(phone="+48123456789", citizenship="Ukraine")
        .with_application(purpose="study", submission_date=date.today())
        .with_initial_payment(amount=500)
        .with_notification(send_email=True)
        .build()
    )
"""

from __future__ import annotations
from datetime import date, time
from decimal import Decimal
from typing import Optional, Dict, Any

from clients.models import Client, Payment
from clients.services.notifications import send_required_documents_email


class ClientBuilder:
    """
    Паттерн Builder для создания клиента со всеми связанными объектами.
    
    Предоставляет fluent interface для пошагового создания клиента
    с автоматическим созданием платежей и отправкой уведомлений.
    """
    
    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._payment_data: Optional[Dict[str, Any]] = None
        self._send_notification = False
        self._auto_create_reminder = True
    
    # === ОСНОВНАЯ ИНФОРМАЦИЯ ===
    
    def with_basic_info(
        self, 
        first_name: str, 
        last_name: str, 
        email: str
    ) -> ClientBuilder:
        """
        Установить базовую информацию о клиенте.
        
        Args:
            first_name: Имя
            last_name: Фамилия
            email: Email (должен быть уникальным)
        
        Returns:
            self для chain вызовов
        """
        self._data.update({
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
        })
        return self
    
    def with_contact(
        self,
        phone: str,
        citizenship: str,
        birth_date: Optional[date] = None,
        employer_phone: Optional[str] = None,
    ) -> ClientBuilder:
        """
        Установить контактные данные.
        
        Args:
            phone: Номер телефона
            citizenship: Гражданство
            birth_date: Дата рождения (опционально)
            employer_phone: Телефон работодателя (опционально)
        
        Returns:
            self для chain вызовов
        """
        self._data.update({
            'phone': phone,
            'citizenship': citizenship,
        })
        if birth_date:
            self._data['birth_date'] = birth_date
        if employer_phone:
            self._data['employer_phone'] = employer_phone
        return self
    
    def with_passport(
        self,
        passport_num: str,
        case_number: Optional[str] = None
    ) -> ClientBuilder:
        """
        Установить паспортные данные.
        
        Args:
            passport_num: Номер паспорта (будет зашифрован)
            case_number: Номер дела (будет зашифрован)
        
        Returns:
            self для chain вызовов
        """
        self._data['passport_num'] = passport_num
        if case_number:
            self._data['case_number'] = case_number
        return self
    
    # === ЗАЯВКА ===
    
    def with_application(
        self,
        purpose: str,
        submission_date: Optional[date] = None,
        basis_of_stay: Optional[str] = None,
        legal_basis_end_date: Optional[date] = None,
        status: str = 'new',
    ) -> ClientBuilder:
        """
        Установить информацию о заявке.
        
        Args:
            purpose: Цель подачи ('study', 'work', 'family' или custom slug)
            submission_date: Дата подачи (опционально)
            basis_of_stay: Основание пребывания (опционально)
            legal_basis_end_date: Дата окончания основания (опционально)
            status: Статус заявки (по умолчанию 'new')
        
        Returns:
            self для chain вызовов
        """
        self._data.update({
            'application_purpose': purpose,
            'status': status,
        })
        if submission_date:
            self._data['submission_date'] = submission_date
        if basis_of_stay:
            self._data['basis_of_stay'] = basis_of_stay
        if legal_basis_end_date:
            self._data['legal_basis_end_date'] = legal_basis_end_date
        return self
    
    def with_fingerprints(
        self,
        fingerprints_date: date,
        fingerprints_time: Optional[time] = None,
        fingerprints_location: Optional[str] = None
    ) -> ClientBuilder:
        """
        Установить информацию об отпечатках.
        
        Args:
            fingerprints_date: Дата сдачи отпечатков
            fingerprints_time: Время сдачи отпечатков (опционально)
            fingerprints_location: Место сдачи отпечатков (опционально)
        
        Returns:
            self для chain вызовов
        """
        self._data['fingerprints_date'] = fingerprints_date
        if fingerprints_time:
            self._data['fingerprints_time'] = fingerprints_time
        if fingerprints_location:
            self._data['fingerprints_location'] = fingerprints_location
        return self
    
    def with_decision_date(self, decision_date: date) -> ClientBuilder:
        """
        Установить дату официальной децизии.
        
        Args:
            decision_date: Дата децизии
        
        Returns:
            self для chain вызовов
        """
        self._data['decision_date'] = decision_date
        return self
    
    def with_language(self, language: str) -> ClientBuilder:
        """
        Установить язык документов.
        
        Args:
            language: Код языка ('ru', 'pl', 'en')
        
        Returns:
            self для chain вызовов
        """
        self._data['language'] = language
        return self
    
    def with_notes(self, notes: str) -> ClientBuilder:
        """
        Добавить заметки.
        
        Args:
            notes: Текст заметок
        
        Returns:
            self для chain вызовов
        """
        self._data['notes'] = notes
        return self
    
    # === ПЛАТЕЖ ===
    
    def with_initial_payment(
        self,
        amount: Decimal | float | int,
        service: Optional[str] = None,
        amount_paid: Decimal | float | int = 0,
        status: str = 'pending',
        payment_method: Optional[str] = None,
        payment_date: Optional[date] = None,
        due_date: Optional[date] = None,
        transaction_id: Optional[str] = None,
    ) -> ClientBuilder:
        """
        Добавить начальный платеж.
        
        Args:
            amount: Общая сумма платежа
            service: Описание услуги (если None - определяется по purpose)
            amount_paid: Уже оплаченная сумма (по умолчанию 0)
            status: Статус платежа ('pending', 'partial', 'paid')
            payment_method: Способ оплаты (опционально)
            payment_date: Дата оплаты (опционально)
            due_date: Срок оплаты (опционально)
            transaction_id: ID транзакции (опционально)
        
        Returns:
            self для chain вызовов
        """
        self._payment_data = {
            'total_amount': Decimal(str(amount)),
            'amount_paid': Decimal(str(amount_paid)),
            'status': status,
        }
        
        # Автоопределение service по purpose (если не указан)
        if service:
            self._payment_data['service_description'] = service
        
        if payment_method:
            self._payment_data['payment_method'] = payment_method
        if payment_date:
            self._payment_data['payment_date'] = payment_date
        if due_date:
            self._payment_data['due_date'] = due_date
        if transaction_id:
            self._payment_data['transaction_id'] = transaction_id
        
        return self
    
    # === НАСТРОЙКИ ===
    
    def with_notification(self, send_email: bool = True) -> ClientBuilder:
        """
        Отправить уведомление после создания.
        
        Args:
            send_email: Отправить email с чеклистом документов
        
        Returns:
            self для chain вызовов
        """
        self._send_notification = send_email
        return self
    
    def with_auto_reminder(self, auto_create: bool = True) -> ClientBuilder:
        """
        Автоматически создавать напоминания.
        
        Args:
            auto_create: Создавать напоминания автоматически
        
        Returns:
            self для chain вызовов
        """
        self._auto_create_reminder = auto_create
        return self
    
    # === ПОСТРОЕНИЕ ===
    
    def build(self) -> Client:
        """
        Создать клиента со всеми связанными объектами.
        
        Выполняет:
        1. Валидацию данных
        2. Создание клиента
        3. Создание начального платежа (если указан)
        4. Отправку уведомления (если включено)
        
        Returns:
            Client: Созданный клиент
        
        Raises:
            ValueError: Если не указаны обязательные поля
        """
        # 1. Валидация
        self._validate()
        
        # 2. Создание клиента
        client = Client.objects.create(**self._data)
        
        # 3. Создание платежа (если указан)
        if self._payment_data:
            # Автоопределение service по application_purpose
            if 'service_description' not in self._payment_data:
                purpose_map = {
                    'work': 'work_service',
                    'study': 'study_service',
                    'family': 'consultation',
                }
                self._payment_data['service_description'] = purpose_map.get(
                    client.application_purpose,
                    'consultation'
                )
            
            Payment.objects.create(
                client=client,
                **self._payment_data
            )
            # Напоминание создастся автоматически через signal
        
        # 4. Отправка уведомления
        if self._send_notification:
            try:
                send_required_documents_email(client)
            except Exception as e:
                # Логируем ошибку, но не прерываем создание клиента
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Failed to send notification email for client {client.id}: {e}"
                )
        
        return client
    
    def _validate(self):
        """
        Валидация данных перед созданием.
        
        Raises:
            ValueError: Если не указаны обязательные поля
        """
        required_fields = ['first_name', 'last_name', 'email', 'phone', 'citizenship']
        missing = [field for field in required_fields if field not in self._data]
        
        if missing:
            raise ValueError(
                f"Не указаны обязательные поля: {', '.join(missing)}"
            )
        
        # Валидация application_purpose (если указан)
        if self._data.get('application_purpose'):
            valid_purposes = ['study', 'work', 'family']
            if self._data['application_purpose'] not in valid_purposes:
                # Проверка в БД (для custom purposes из Submission)
                from submissions.models import Submission
                if not Submission.objects.filter(
                    slug=self._data['application_purpose']
                ).exists():
                    raise ValueError(
                        f"Неверная цель подачи: {self._data['application_purpose']}. "
                        f"Допустимые значения: {', '.join(valid_purposes)} "
                        f"или существующий slug из Submission"
                    )
