"""
ClientService - Высокоуровневый сервис для управления клиентами.

Координирует взаимодействие между различными компонентами системы.
Использование:
    # Создание клиента
    client = ClientService.create_new_client(
        first_name="Иван",
        last_name="Петров",
        email="ivan@example.com",
        phone="+48123456789",
        citizenship="Ukraine",
        application_purpose="study",
        initial_payment_amount=Decimal('500')
    )
    
    # Получение сводки
    summary = ClientService.get_client_summary(client)
"""

from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any

from django.utils import timezone

from clients.models import Client, Payment, Document
from clients.services.builders.client_builder import ClientBuilder
from clients.services.builders.payment_builder import PaymentBuilder
from clients.services.notifications import (
    send_required_documents_email,
    send_missing_documents_email,
    send_expiring_documents_email,
)


class ClientService:
    """
    Сервис для управления клиентами и связанными операциями.
    
    Предоставляет высокоуровневые методы для:
    - Создания клиентов с автоматической настройкой
    - Управления платежами
    - Проверки документов
    - Отправки уведомлений
    - Получения аналитики
    """
    
    @staticmethod
    def create_new_client(
        first_name: str,
        last_name: str,
        email: str,
        phone: str,
        citizenship: str,
        application_purpose: str,
        initial_payment_amount: Optional[Decimal | float | int] = None,
        send_welcome_email: bool = True,
        **extra_fields
    ) -> Client:
        """
        Создать нового клиента с автоматической настройкой всех компонентов.
        
        Автоматически:
        - Создает клиента
        - Добавляет начальный платеж (если указан)
        - Отправляет welcome email (если включено)
        - Reminder создастся автоматически через signal
        
        Args:
            first_name: Имя
            last_name: Фамилия
            email: Email (должен быть уникальным)
            phone: Телефон
            citizenship: Гражданство
            application_purpose: Цель подачи
            initial_payment_amount: Начальный платеж (опционально)
            send_welcome_email: Отправить приветственный email
            **extra_fields: Дополнительные поля (passport_num, case_number, etc.)
        
        Returns:
            Client: Созданный клиент со всеми связанными объектами
        
        Raises:
            ValueError: Если данные невалидны
        
        Example:
            >>> client = ClientService.create_new_client(
            ...     first_name="Иван",
            ...     last_name="Петров",
            ...     email="ivan@test.com",
            ...     phone="+48123456789",
            ...     citizenship="Ukraine",
            ...     application_purpose="study",
            ...     initial_payment_amount=Decimal('500'),
            ...     passport_num="AA1234567"
            ... )
        """
        # Использование Builder
        builder = (
            ClientBuilder()
            .with_basic_info(first_name, last_name, email)
            .with_contact(phone, citizenship)
            .with_application(purpose=application_purpose)
        )
        
        # Добавление опциональных полей
        if 'passport_num' in extra_fields:
            builder.with_passport(
                passport_num=extra_fields['passport_num'],
                case_number=extra_fields.get('case_number')
            )
        
        if 'birth_date' in extra_fields:
            builder._data['birth_date'] = extra_fields['birth_date']
        
        if 'employer_phone' in extra_fields:
            builder._data['employer_phone'] = extra_fields['employer_phone']
        
        if 'language' in extra_fields:
            builder.with_language(extra_fields['language'])
        
        if 'notes' in extra_fields:
            builder.with_notes(extra_fields['notes'])
        
        if 'submission_date' in extra_fields:
            builder._data['submission_date'] = extra_fields['submission_date']
        
        if 'basis_of_stay' in extra_fields:
            builder._data['basis_of_stay'] = extra_fields['basis_of_stay']
        
        # Начальный платеж
        if initial_payment_amount:
            builder.with_initial_payment(amount=initial_payment_amount)
        
        # Уведомление
        if send_welcome_email:
            builder.with_notification(send_email=True)
        
        return builder.build()
    
    @staticmethod
    def add_payment_to_client(
        client: Client,
        amount: Decimal | float | int,
        service: Optional[str] = None,
        partial_payment: Optional[Decimal | float | int] = None,
        due_date: Optional[date] = None,
        payment_method: Optional[str] = None,
    ) -> Payment:
        """
        Добавить платеж клиенту.
        
        Args:
            client: Клиент
            amount: Общая сумма
            service: Описание услуги (если None - определяется по purpose)
            partial_payment: Частичная оплата (опционально)
            due_date: Срок оплаты (опционально)
            payment_method: Способ оплаты (опционально)
        
        Returns:
            Payment: Созданный платеж
        
        Example:
            >>> payment = ClientService.add_payment_to_client(
            ...     client=client,
            ...     amount=Decimal('1000'),
            ...     partial_payment=Decimal('500'),
            ...     due_date=date(2024, 12, 31)
            ... )
        """
        builder = PaymentBuilder(client).for_service(service, amount=amount)
        
        if partial_payment:
            builder.with_partial_payment(
                amount=partial_payment,
                payment_method=payment_method
            )
        
        if due_date:
            builder.with_due_date(due_date)
        
        return builder.build()
    
    @staticmethod
    def update_application_purpose(
        client: Client,
        new_purpose: str,
    ) -> Client:
        """
        Обновить цель подачи с автоматической синхронизацией платежей.
        
        Signal автоматически обновит service_description для pending платежей.
        
        Args:
            client: Клиент
            new_purpose: Новая цель подачи
        
        Returns:
            Client: Обновленный клиент
        
        Example:
            >>> ClientService.update_application_purpose(client, 'work')
        """
        client.application_purpose = new_purpose
        client.save(update_fields=['application_purpose'])
        return client
    
    @staticmethod
    def check_missing_documents(client: Client) -> List[Dict[str, Any]]:
        """
        Проверить недостающие документы.
        
        Args:
            client: Клиент
        
        Returns:
            List[Dict]: Список недостающих документов
        
        Example:
            >>> missing = ClientService.check_missing_documents(client)
            >>> print(f"Недостает {len(missing)} документов")
        """
        checklist = client.get_document_checklist()
        missing = [item for item in checklist if not item['is_uploaded']]
        return missing
    
    @staticmethod
    def send_missing_documents_reminder(client: Client) -> bool:
        """
        Отправить напоминание о недостающих документах.
        
        Args:
            client: Клиент
        
        Returns:
            bool: True если были недостающие документы и email отправлен
        
        Example:
            >>> if ClientService.send_missing_documents_reminder(client):
            ...     print("Напоминание отправлено")
        """
        missing = ClientService.check_missing_documents(client)
        
        if missing:
            try:
                send_missing_documents_email(client)
                return True
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send missing docs email: {e}")
                return False
        return False
    
    @staticmethod
    def check_expiring_documents(
        client: Client,
        days_ahead: int = 30
    ) -> List[Document]:
        """
        Проверить истекающие документы.
        
        Args:
            client: Клиент
            days_ahead: Количество дней вперед для проверки
        
        Returns:
            List[Document]: Список документов, срок которых истекает
        
        Example:
            >>> expiring = ClientService.check_expiring_documents(client, days_ahead=7)
            >>> if expiring:
            ...     print(f"Истекает {len(expiring)} документов")
        """
        threshold_date = timezone.now().date() + timedelta(days=days_ahead)
        
        expiring = client.documents.filter(
            expiry_date__isnull=False,
            expiry_date__lte=threshold_date,
            expiry_date__gte=timezone.now().date(),
        )
        
        return list(expiring)
    
    @staticmethod
    def get_client_summary(client: Client) -> Dict[str, Any]:
        """
        Получить полную сводку по клиенту.
        
        Включает:
        - Информацию о платежах
        - Информацию о документах
        - Активные напоминания
        - Статус заявки
        
        Args:
            client: Клиент
        
        Returns:
            Dict: Сводка с метриками
        
        Example:
            >>> summary = ClientService.get_client_summary(client)
            >>> print(f"Оплачено: {summary['payments']['total_paid']}")
            >>> print(f"Осталось: {summary['payments']['total_due']}")
        """
        payments = client.payments.all()
        documents = client.documents.all()
        reminders = client.reminders.filter(is_active=True)
        
        total_paid = sum(p.amount_paid for p in payments)
        total_due = sum(p.amount_due for p in payments)
        
        missing_docs = ClientService.check_missing_documents(client)
        expiring_docs = ClientService.check_expiring_documents(client)
        
        return {
            'client': client,
            'payments': {
                'total': payments.count(),
                'total_paid': total_paid,
                'total_due': total_due,
                'pending': payments.filter(status='pending').count(),
                'partial': payments.filter(status='partial').count(),
                'paid': payments.filter(status='paid').count(),
            },
            'documents': {
                'total': documents.count(),
                'verified': documents.filter(verified=True).count(),
                'awaiting_confirmation': documents.filter(
                    awaiting_confirmation=True
                ).count(),
                'missing': len(missing_docs),
                'expiring_soon': len(expiring_docs),
            },
            'reminders': {
                'active': reminders.count(),
                'payment_reminders': reminders.filter(
                    reminder_type='payment'
                ).count(),
                'document_reminders': reminders.filter(
                    reminder_type='document'
                ).count(),
                'other_reminders': reminders.filter(
                    reminder_type='other'
                ).count(),
            },
            'status': {
                'application_status': client.status,
                'application_purpose': client.get_application_purpose_display(),
                'has_pending_tasks': len(missing_docs) > 0 or reminders.exists(),
                'needs_attention': (
                    total_due > 0 or
                    len(missing_docs) > 0 or
                    len(expiring_docs) > 0
                ),
            }
        }
