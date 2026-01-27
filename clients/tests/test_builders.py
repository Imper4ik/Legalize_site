"""
Тесты для Builder Pattern и ClientService.

Запуск:
    pytest clients/tests/test_builders.py -v
    или
    python manage.py test clients.tests.test_builders
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import TestCase

from clients.models import Client, Payment, Reminder
from clients.services.builders import ClientBuilder, PaymentBuilder
from clients.services.orchestrators import ClientService


class ClientBuilderTestCase(TestCase):
    """Тесты для ClientBuilder."""
    
    def test_basic_client_creation(self):
        """Тест создания базового клиента."""
        client = (
            ClientBuilder()
            .with_basic_info("Test", "User", "test@example.com")
            .with_contact("+48123456789", "Ukraine")
            .with_application(purpose="study")
            .build()
        )
        
        self.assertIsNotNone(client.id)
        self.assertEqual(client.first_name, "Test")
        self.assertEqual(client.last_name, "User")
        self.assertEqual(client.email, "test@example.com")
        self.assertEqual(client.phone, "+48123456789")
        self.assertEqual(client.citizenship, "Ukraine")
        self.assertEqual(client.application_purpose, "study")
    
    def test_client_with_payment(self):
        """Тест создания клиента с платежом."""
        client = (
            ClientBuilder()
            .with_basic_info("Test", "User", "test2@example.com")
            .with_contact("+48987654321", "Belarus")
            .with_application(purpose="work")
            .with_initial_payment(
                amount=Decimal('1000'),
                amount_paid=Decimal('500')
            )
            .build()
        )
        
        self.assertEqual(client.payments.count(), 1)
        
        payment = client.payments.first()
        self.assertEqual(payment.total_amount, Decimal('1000'))
        self.assertEqual(payment.amount_paid, Decimal('500'))
        self.assertEqual(payment.status, 'partial')
        self.assertEqual(payment.service_description, 'work_service')
    
    def test_client_with_auto_service_mapping(self):
        """Тест автоматического определения service по purpose."""
        # Study -> study_service
        client1 = (
            ClientBuilder()
            .with_basic_info("Test1", "User", "test3@example.com")
            .with_contact("+48111111111", "Ukraine")
            .with_application(purpose="study")
            .with_initial_payment(amount=Decimal('500'))
            .build()
        )
        self.assertEqual(
            client1.payments.first().service_description,
            'study_service'
        )
        
        # Work -> work_service
        client2 = (
            ClientBuilder()
            .with_basic_info("Test2", "User", "test4@example.com")
            .with_contact("+48222222222", "Ukraine")
            .with_application(purpose="work")
            .with_initial_payment(amount=Decimal('500'))
            .build()
        )
        self.assertEqual(
            client2.payments.first().service_description,
            'work_service'
        )
        
        # Family -> consultation
        client3 = (
            ClientBuilder()
            .with_basic_info("Test3", "User", "test5@example.com")
            .with_contact("+48333333333", "Ukraine")
            .with_application(purpose="family")
            .with_initial_payment(amount=Decimal('500'))
            .build()
        )
        self.assertEqual(
            client3.payments.first().service_description,
            'consultation'
        )
    
    def test_client_validation(self):
        """Тест валидации обязательных полей."""
        with self.assertRaises(ValueError) as context:
            ClientBuilder().build()
        
        self.assertIn("обязательные поля", str(context.exception).lower())
    
    def test_client_with_passport(self):
        """Тест создания клиента с паспортными данными."""
        client = (
            ClientBuilder()
            .with_basic_info("Test", "User", "test6@example.com")
            .with_contact("+48444444444", "Ukraine")
            .with_passport(
                passport_num="AA1234567",
                case_number="WRO-2024-00123"
            )
            .with_application(purpose="study")
            .build()
        )
        
        self.assertEqual(client.passport_num, "AA1234567")
        self.assertEqual(client.case_number, "WRO-2024-00123")
        # case_number_hash создается автоматически
        self.assertIsNotNone(client.case_number_hash)
    
    def test_client_with_fingerprints(self):
        """Тест создания клиента с информацией об отпечатках."""
        fingerprint_date = date.today() + timedelta(days=7)
        
        client = (
            ClientBuilder()
            .with_basic_info("Test", "User", "test7@example.com")
            .with_contact("+48555555555", "Ukraine")
            .with_application(purpose="study")
            .with_fingerprints(
                fingerprints_date=fingerprint_date,
                fingerprints_location="Wrocław"
            )
            .build()
        )
        
        self.assertEqual(client.fingerprints_date, fingerprint_date)
        self.assertEqual(client.fingerprints_location, "Wrocław")


class PaymentBuilderTestCase(TestCase):
    """Тесты для PaymentBuilder."""
    
    def setUp(self):
        """Создать тестового клиента."""
        self.client = Client.objects.create(
            first_name="Test",
            last_name="Client",
            email="testclient@example.com",
            phone="+48123456789",
            citizenship="Ukraine",
            application_purpose="study"
        )
    
    def test_basic_payment_creation(self):
        """Тест создания базового платежа."""
        payment = (
            PaymentBuilder(self.client)
            .for_service("study_service", amount=Decimal('1000'))
            .build()
        )
        
        self.assertIsNotNone(payment.id)
        self.assertEqual(payment.client, self.client)
        self.assertEqual(payment.total_amount, Decimal('1000'))
        self.assertEqual(payment.service_description, 'study_service')
        self.assertEqual(payment.status, 'pending')
    
    def test_payment_with_partial_payment(self):
        """Тест создания платежа с частичной оплатой."""
        payment = (
            PaymentBuilder(self.client)
            .for_service("work_service", amount=Decimal('1000'))
            .with_partial_payment(
                amount=Decimal('600'),
                payment_method='card'
            )
            .build()
        )
        
        self.assertEqual(payment.amount_paid, Decimal('600'))
        self.assertEqual(payment.status, 'partial')
        self.assertEqual(payment.payment_method, 'card')
        self.assertEqual(payment.amount_due, Decimal('400'))
    
    def test_payment_status_auto_calculation(self):
        """Тест автоматического определения статуса."""
        # Pending (не оплачен)
        payment1 = (
            PaymentBuilder(self.client)
            .for_service("consultation", amount=Decimal('500'))
            .build()
        )
        self.assertEqual(payment1.status, 'pending')
        
        # Partial (частично оплачен)
        payment2 = (
            PaymentBuilder(self.client)
            .for_service("consultation", amount=Decimal('500'))
            .with_partial_payment(amount=Decimal('250'))
            .build()
        )
        self.assertEqual(payment2.status, 'partial')
        
        # Paid (оплачен полностью)
        payment3 = (
            PaymentBuilder(self.client)
            .for_service("consultation", amount=Decimal('500'))
            .with_partial_payment(amount=Decimal('500'))
            .build()
        )
        self.assertEqual(payment3.status, 'paid')
        
        # Paid (переплата)
        payment4 = (
            PaymentBuilder(self.client)
            .for_service("consultation", amount=Decimal('500'))
            .with_partial_payment(amount=Decimal('600'))
            .build()
        )
        self.assertEqual(payment4.status, 'paid')
    
    def test_payment_as_paid(self):
        """Тест метода as_paid."""
        payment = (
            PaymentBuilder(self.client)
            .for_service("study_service", amount=Decimal('1000'))
            .as_paid(
                payment_date=date.today(),
                payment_method='transfer'
            )
            .build()
        )
        
        self.assertEqual(payment.status, 'paid')
        self.assertEqual(payment.amount_paid, Decimal('1000'))
        self.assertEqual(payment.payment_method, 'transfer')
    
    def test_payment_auto_reminder_creation(self):
        """Тест автоматического создания напоминания через signal."""
        payment = (
            PaymentBuilder(self.client)
            .for_service("study_service", amount=Decimal('1000'))
            .with_partial_payment(amount=Decimal('500'))
            .with_due_date(date.today() + timedelta(days=30))
            .build()
        )
        
        # Signal должен создать reminder для partial payment
        self.assertEqual(payment.status, 'partial')
        
        # Проверяем что reminder создался
        reminders = Reminder.objects.filter(payment=payment)
        self.assertEqual(reminders.count(), 1)
        
        reminder = reminders.first()
        self.assertEqual(reminder.client, self.client)
        self.assertEqual(reminder.reminder_type, 'payment')


class ClientServiceTestCase(TestCase):
    """Тесты для ClientService."""
    
    def test_create_new_client(self):
        """Тест создания клиента через сервис."""
        client = ClientService.create_new_client(
            first_name="Service",
            last_name="Test",
            email="service@example.com",
            phone="+48999999999",
            citizenship="Ukraine",
            application_purpose="study",
            send_welcome_email=False
        )
        
        self.assertIsNotNone(client.id)
        self.assertEqual(client.first_name, "Service")
        self.assertEqual(client.email, "service@example.com")
    
    def test_create_client_with_payment(self):
        """Тест создания клиента с платежом через сервис."""
        client = ClientService.create_new_client(
            first_name="Service",
            last_name="Test2",
            email="service2@example.com",
            phone="+48888888888",
            citizenship="Belarus",
            application_purpose="work",
            initial_payment_amount=Decimal('1500'),
            send_welcome_email=False
        )
        
        self.assertEqual(client.payments.count(), 1)
        payment = client.payments.first()
        self.assertEqual(payment.total_amount, Decimal('1500'))
    
    def test_add_payment_to_client(self):
        """Тест добавления платежа к клиенту."""
        client = Client.objects.create(
            first_name="Test",
            last_name="User",
            email="addpayment@example.com",
            phone="+48777777777",
            citizenship="Moldova",
            application_purpose="family"
        )
        
        payment = ClientService.add_payment_to_client(
            client=client,
            amount=Decimal('800'),
            partial_payment=Decimal('400')
        )
        
        self.assertEqual(payment.client, client)
        self.assertEqual(payment.total_amount, Decimal('800'))
        self.assertEqual(payment.amount_paid, Decimal('400'))
    
    def test_get_client_summary(self):
        """Тест получения сводки по клиенту."""
        client = ClientService.create_new_client(
            first_name="Summary",
            last_name="Test",
            email="summary@example.com",
            phone="+48666666666",
            citizenship="Ukraine",
            application_purpose="study",
            initial_payment_amount=Decimal('1000'),
            send_welcome_email=False
        )
        
        summary = ClientService.get_client_summary(client)
        
        self.assertIn('client', summary)
        self.assertIn('payments', summary)
        self.assertIn('documents', summary)
        self.assertIn('reminders', summary)
        self.assertIn('status', summary)
        
        self.assertEqual(summary['payments']['total'], 1)
        self.assertEqual(summary['payments']['total_due'], Decimal('1000'))
    
    def test_check_missing_documents(self):
        """Тест проверки недостающих документов."""
        client = Client.objects.create(
            first_name="Test",
            last_name="Docs",
            email="docs@example.com",
            phone="+48555555555",
            citizenship="Ukraine",
            application_purpose="study"
        )
        
        missing = ClientService.check_missing_documents(client)
        
        # Должны быть недостающие документы для study
        self.assertGreater(len(missing), 0)
        self.assertIsInstance(missing, list)


# Для запуска через pytest
@pytest.mark.django_db
class TestClientBuilderPytest:
    """Pytest тесты (альтернатива)."""
    
    def test_builder_fluent_interface(self):
        """Тест fluent interface."""
        client = (
            ClientBuilder()
            .with_basic_info("Fluent", "Test", "fluent@example.com")
            .with_contact("+48444444444", "Ukraine")
            .with_application("study")
            .with_language("ru")
            .with_notes("Test notes")
            .build()
        )
        
        assert client.first_name == "Fluent"
        assert client.language == "ru"
        assert client.notes == "Test notes"
