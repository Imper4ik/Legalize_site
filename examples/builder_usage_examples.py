"""
Примеры использования Builder Pattern и ClientService.

Для запуска:
    python manage.py shell < examples/builder_usage_examples.py
    
Или в shell:
    from examples.builder_usage_examples import *
    example1_basic_client()
"""

from datetime import date, timedelta
from decimal import Decimal

from clients.services.builders import ClientBuilder, PaymentBuilder
from clients.services.orchestrators import ClientService


def example1_basic_client():
    """
    Пример 1: Создание базового клиента.
    """
    print("=" * 60)
    print("ПРИМЕР 1: Создание базового клиента")
    print("=" * 60)
    
    client = (
        ClientBuilder()
        .with_basic_info(
            first_name="Иван",
            last_name="Петров",
            email="ivan.petrov@example.com"
        )
        .with_contact(
            phone="+48123456789",
            citizenship="Ukraine"
        )
        .with_application(purpose="study")
        .build()
    )
    
    print(f"✅ Создан клиент: {client}")
    print(f"   Email: {client.email}")
    print(f"   Телефон: {client.phone}")
    print(f"   Цель: {client.get_application_purpose_display()}")
    print()
    return client


def example2_client_with_payment():
    """
    Пример 2: Создание клиента с начальным платежом.
    """
    print("=" * 60)
    print("ПРИМЕР 2: Клиент с начальным платежом")
    print("=" * 60)
    
    client = (
        ClientBuilder()
        .with_basic_info(
            "Мария",
            "Коваль",
            "maria.koval@example.com"
        )
        .with_contact(
            phone="+48987654321",
            citizenship="Ukraine"
        )
        .with_passport(
            passport_num="AA7654321",
            case_number="WRO-2024-00123"
        )
        .with_application(
            purpose="study",
            submission_date=date.today()
        )
        .with_initial_payment(
            amount=Decimal('1200'),
            amount_paid=Decimal('600'),  # Частичная оплата
            due_date=date.today() + timedelta(days=30)
        )
        .with_notification(send_email=False)  # Отключаем email для примера
        .build()
    )
    
    payment = client.payments.first()
    
    print(f"✅ Создан клиент: {client}")
    print(f"   Платеж: {payment}")
    print(f"   Общая сумма: {payment.total_amount} zł")
    print(f"   Оплачено: {payment.amount_paid} zł")
    print(f"   Осталось: {payment.amount_due} zł")
    print(f"   Статус: {payment.get_status_display()}")
    
    # Проверяем что reminder создался автоматически
    reminder = client.reminders.first()
    if reminder:
        print(f"   Напоминание: {reminder.title}")
    print()
    return client


def example3_full_featured_client():
    """
    Пример 3: Полнофункциональный клиент со всеми полями.
    """
    print("=" * 60)
    print("ПРИМЕР 3: Полнофункциональный клиент")
    print("=" * 60)
    
    client = (
        ClientBuilder()
        .with_basic_info("Олег", "Сидоров", "oleg.sidorov@example.com")
        .with_contact(
            phone="+48111222333",
            citizenship="Belarus",
            birth_date=date(1995, 3, 15)
        )
        .with_passport(
            passport_num="BB9876543",
            case_number="WRO-2024-00456"
        )
        .with_application(
            purpose="work",
            submission_date=date.today(),
            basis_of_stay="Work Permit Type A",
            legal_basis_end_date=date(2025, 12, 31)
        )
        .with_fingerprints(
            fingerprints_date=date.today() + timedelta(days=14),
            fingerprints_location="Wrocław, ul. Piłsudskiego 22"
        )
        .with_language("ru")
        .with_notes("Клиент из Минска, работает программистом")
        .with_initial_payment(
            amount=Decimal('1500'),
            service="work_service",
            amount_paid=Decimal('750'),
            payment_method="card",
            payment_date=date.today()
        )
        .with_notification(send_email=False)
        .build()
    )
    
    print(f"✅ Создан клиент: {client}")
    print(f"   Номер дела: {client.case_number}")
    print(f"   Основание: {client.basis_of_stay}")
    print(f"   Отпечатки: {client.fingerprints_date}")
    print(f"   Язык: {client.get_language_display()}")
    print()
    return client


def example4_using_service():
    """
    Пример 4: Использование ClientService (упрощенный API).
    """
    print("=" * 60)
    print("ПРИМЕР 4: Использование ClientService")
    print("=" * 60)
    
    # Создание клиента в одну строку
    client = ClientService.create_new_client(
        first_name="Анна",
        last_name="Волкова",
        email="anna.volkova@example.com",
        phone="+48444555666",
        citizenship="Ukraine",
        application_purpose="study",
        initial_payment_amount=Decimal('1000'),
        send_welcome_email=False,
        # Дополнительные поля
        passport_num="CC1122334",
        language="ru",
        notes="Студентка Warsaw University"
    )
    
    print(f"✅ Создан клиент через сервис: {client}")
    
    # Получение сводки
    summary = ClientService.get_client_summary(client)
    
    print(f"\n📊 Сводка:")
    print(f"   Платежи: {summary['payments']['total']} шт.")
    print(f"   Оплачено: {summary['payments']['total_paid']} zł")
    print(f"   Осталось: {summary['payments']['total_due']} zł")
    print(f"   Документы: {summary['documents']['total']} шт.")
    print(f"   Недостает: {summary['documents']['missing']} шт.")
    print(f"   Напоминания: {summary['reminders']['active']} шт.")
    print(f"   Требует внимания: {summary['status']['needs_attention']}")
    print()
    return client


def example5_adding_payment():
    """
    Пример 5: Добавление платежа к существующему клиенту.
    """
    print("=" * 60)
    print("ПРИМЕР 5: Добавление платежа")
    print("=" * 60)
    
    # Создаем клиента без платежа
    client = (
        ClientBuilder()
        .with_basic_info("Петр", "Иванов", "petr.ivanov@example.com")
        .with_contact("+48777888999", "Moldova")
        .with_application(purpose="family")
        .build()
    )
    
    print(f"✅ Создан клиент: {client}")
    print(f"   Платежей: {client.payments.count()}")
    
    # Добавляем платеж через сервис
    payment = ClientService.add_payment_to_client(
        client=client,
        amount=Decimal('800'),
        partial_payment=Decimal('400'),
        due_date=date.today() + timedelta(days=30)
    )
    
    print(f"\n✅ Добавлен платеж:")
    print(f"   Услуга: {payment.get_service_description_display()}")
    print(f"   Сумма: {payment.total_amount} zł")
    print(f"   Оплачено: {payment.amount_paid} zł")
    print(f"   Статус: {payment.get_status_display()}")
    
    # Добавляем еще один платеж через Builder
    payment2 = (
        PaymentBuilder(client)
        .for_service("consultation", amount=Decimal('200'))
        .as_paid(
            payment_date=date.today(),
            payment_method="cash"
        )
        .build()
    )
    
    print(f"\n✅ Добавлен второй платеж:")
    print(f"   Услуга: {payment2.get_service_description_display()}")
    print(f"   Статус: {payment2.get_status_display()}")
    print(f"\n   Всего платежей: {client.payments.count()}")
    print()
    return client


def example6_checking_documents():
    """
    Пример 6: Проверка недостающих документов.
    """
    print("=" * 60)
    print("ПРИМЕР 6: Проверка документов")
    print("=" * 60)
    
    client = ClientService.create_new_client(
        first_name="Елена",
        last_name="Новикова",
        email="elena.novikova@example.com",
        phone="+48222333444",
        citizenship="Russia",
        application_purpose="study",
        send_welcome_email=False
    )
    
    print(f"✅ Создан клиент: {client}")
    
    # Проверка недостающих документов
    missing = ClientService.check_missing_documents(client)
    
    print(f"\n📄 Недостающие документы ({len(missing)}):")
    for doc in missing[:5]:  # Показываем первые 5
        print(f"   - {doc['name']}")
    
    if len(missing) > 5:
        print(f"   ... и еще {len(missing) - 5}")
    
    # Проверка истекающих документов (пока нет)
    expiring = ClientService.check_expiring_documents(client, days_ahead=30)
    print(f"\n⏰ Истекающие документы: {len(expiring)} шт.")
    print()
    return client


def run_all_examples():
    """
    Запустить все примеры.
    """
    print("\n" + "=" * 60)
    print("ЗАПУСК ВСЕХ ПРИМЕРОВ")
    print("=" * 60 + "\n")
    
    try:
        example1_basic_client()
        example2_client_with_payment()
        example3_full_featured_client()
        example4_using_service()
        example5_adding_payment()
        example6_checking_documents()
        
        print("=" * 60)
        print("✅ ВСЕ ПРИМЕРЫ ВЫПОЛНЕНЫ УСПЕШНО!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_examples()
