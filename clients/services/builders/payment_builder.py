"""
PaymentBuilder - Паттерн Builder для создания платежей.

Использование:
    payment = (
        PaymentBuilder(client)
        .for_service("study_service", amount=1000)
        .with_partial_payment(amount=500)
        .with_due_date(due_date=date(2024, 12, 31))
        .build()
    )
"""

from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Optional

from clients.models import Client, Payment


class PaymentBuilder:
    """
    Паттерн Builder для создания платежей с автоматическими расчетами.
    
    Автоматически определяет статус платежа на основе оплаченной суммы.
    """
    
    def __init__(self, client: Client):
        """
        Инициализация строителя платежа.
        
        Args:
            client: Клиент, для которого создается платеж
        """
        self.client = client
        self._data = {
            'client': client,
            'amount_paid': Decimal('0'),
            'status': 'pending',
        }
    
    def for_service(
        self,
        service: Optional[str] = None,
        amount: Optional[Decimal | float | int] = None,
        auto_sync_from_purpose: bool = True
    ) -> PaymentBuilder:
        """
        Установить услугу и сумму.
        
        Args:
            service: Описание услуги (work_service, study_service, consultation)
                    Если None и auto_sync=True - берется из client.application_purpose
            amount: Общая сумма платежа
            auto_sync_from_purpose: Автоматически определять service из purpose
        
        Returns:
            self для chain вызовов
        """
        # Если не указан service, но auto_sync включен - берем из client
        if not service and auto_sync_from_purpose:
            purpose_map = {
                'work': 'work_service',
                'study': 'study_service',
                'family': 'consultation',
            }
            service = purpose_map.get(
                self.client.application_purpose,
                'consultation'
            )
        
        if service:
            self._data['service_description'] = service
        
        if amount is not None:
            self._data['total_amount'] = Decimal(str(amount))
        
        return self
    
    def with_partial_payment(
        self,
        amount: Decimal | float | int,
        payment_date: Optional[date] = None,
        payment_method: Optional[str] = None,
        transaction_id: Optional[str] = None,
    ) -> PaymentBuilder:
        """
        Добавить частичную оплату.
        
        Автоматически определяет статус:
        - 'paid' если amount >= total_amount
        - 'partial' если 0 < amount < total_amount
        - 'pending' если amount = 0
        
        Args:
            amount: Оплаченная сумма
            payment_date: Дата оплаты (опционально)
            payment_method: Способ оплаты (опционально)
            transaction_id: ID транзакции (опционально)
        
        Returns:
            self для chain вызовов
        """
        self._data['amount_paid'] = Decimal(str(amount))
        
        # Автоопределение статуса
        total = self._data.get('total_amount', Decimal('0'))
        if total > 0:
            if self._data['amount_paid'] >= total:
                self._data['status'] = 'paid'
            elif self._data['amount_paid'] > 0:
                self._data['status'] = 'partial'
            else:
                self._data['status'] = 'pending'
        
        if payment_date:
            self._data['payment_date'] = payment_date
        if payment_method:
            self._data['payment_method'] = payment_method
        if transaction_id:
            self._data['transaction_id'] = transaction_id
        
        return self
    
    def with_due_date(self, due_date: date) -> PaymentBuilder:
        """
        Установить срок оплаты.
        
        Args:
            due_date: Дата, до которой нужно оплатить
        
        Returns:
            self для chain вызовов
        """
        self._data['due_date'] = due_date
        return self
    
    def as_pending(self) -> PaymentBuilder:
        """
        Установить статус: ожидает оплаты.
        
        Returns:
            self для chain вызовов
        """
        self._data['status'] = 'pending'
        self._data['amount_paid'] = Decimal('0')
        return self
    
    def as_paid(
        self,
        payment_date: Optional[date] = None,
        payment_method: Optional[str] = None,
        transaction_id: Optional[str] = None,
    ) -> PaymentBuilder:
        """
        Установить статус: оплачен полностью.
        
        Args:
            payment_date: Дата оплаты (опционально)
            payment_method: Способ оплаты (опционально)
            transaction_id: ID транзакции (опционально)
        
        Returns:
            self для chain вызовов
        """
        self._data['status'] = 'paid'
        total = self._data.get('total_amount', Decimal('0'))
        self._data['amount_paid'] = total
        
        if payment_date:
            self._data['payment_date'] = payment_date
        if payment_method:
            self._data['payment_method'] = payment_method
        if transaction_id:
            self._data['transaction_id'] = transaction_id
        
        return self
    
    def build(self) -> Payment:
        """
        Создать платеж.
        
        Returns:
            Payment: Созданный платеж
        
        Raises:
            ValueError: Если не указаны обязательные поля
        """
        # Валидация
        if 'service_description' not in self._data:
            raise ValueError("Не указано описание услуги (service_description)")
        if 'total_amount' not in self._data:
            raise ValueError("Не указана общая сумма (total_amount)")
        
        # Создание платежа
        # Signal автоматически создаст reminder если status='partial'
        return Payment.objects.create(**self._data)
