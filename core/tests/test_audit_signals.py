"""
Tests for audit signal handlers.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from clients.models import Client, Payment
from core.models import AuditLog
from core.audit_signals import set_current_request, clear_current_request
from django.test import RequestFactory
from decimal import Decimal

User = get_user_model()


class AuditSignalsTest(TestCase):
    """Test automatic audit logging via signals."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com'
        )
        self.factory = RequestFactory()
        
        # Create a mock request
        request = self.factory.get('/')
        request.user = self.user
        set_current_request(request)
    
    def tearDown(self):
        """Clean up."""
        clear_current_request()
    
    def test_client_create_signal(self):
        """Test that creating a client creates an audit log."""
        initial_count = AuditLog.objects.count()
        
        client = Client.objects.create(
            first_name='Тест',
            last_name='Тестов',
            email='test@example.com',
            phone='+48123456789',
            citizenship='RU',
            application_purpose='work'
        )
        
        # Check that a log was created
        self.assertEqual(AuditLog.objects.count(), initial_count + 1)
        
        log = AuditLog.objects.latest('timestamp')
        self.assertEqual(log.action, AuditLog.Action.CREATE)
        self.assertEqual(log.user, self.user)
        self.assertIn(client.email, log.object_repr)
    
    def test_client_update_signal(self):
        """Test that updating a client creates an audit log."""
        client = Client.objects.create(
            first_name='Тест',
            last_name='Тестов',
            email='test@example.com',
            phone='+48123456789',
            citizenship='RU',
            application_purpose='work'
        )
        
        initial_count = AuditLog.objects.count()
        
        # Update client
        client.status = 'active'
        client.save()
        
        # Check that an UPDATE log was created
        self.assertEqual(AuditLog.objects.count(), initial_count + 1)
        
        log = AuditLog.objects.latest('timestamp')
        self.assertEqual(log.action, AuditLog.Action.UPDATE)
        self.assertIsNotNone(log.changes)
        self.assertIn('status', log.changes)
    
    def test_client_delete_signal(self):
        """Test that deleting a client creates an audit log."""
        client = Client.objects.create(
            first_name='Тест',
            last_name='Тестов',
            email='test@example.com',
            phone='+48123456789',
            citizenship='RU',
            application_purpose='work'
        )
        
        client_str = str(client)
        initial_count = AuditLog.objects.count()
        
        client.delete()
        
        # Check that a DELETE log was created
        self.assertEqual(AuditLog.objects.count(), initial_count + 1)
        
        log = AuditLog.objects.latest('timestamp')
        self.assertEqual(log.action, AuditLog.Action.DELETE)
        self.assertIn(client_str, str(log.changes))
    
    def test_payment_create_signal(self):
        """Test that creating a payment creates an audit log."""
        client = Client.objects.create(
            first_name='Тест',
            last_name='Тестов',
            email='test@example.com',
            phone='+48123456789',
            citizenship='RU',
            application_purpose='work'
        )
        
        initial_count = AuditLog.objects.count()
        
        payment = Payment.objects.create(
            client=client,
            total_amount=Decimal('1000.00'),
            service_description='Test service'
        )
        
        # Check that a log was created
        self.assertGreater(AuditLog.objects.count(), initial_count)
        
        log = AuditLog.objects.filter(action=AuditLog.Action.CREATE).latest('timestamp')
        self.assertIsNotNone(log.changes)
        self.assertIn('total_amount', log.changes)
    
    def test_payment_update_tracks_changes(self):
        """Test that payment updates track specific field changes."""
        client = Client.objects.create(
            first_name='Тест',
            last_name='Тестов',
            email='test@example.com',
            phone='+48123456789',
            citizenship='RU',
            application_purpose='work'
        )
        
        payment = Payment.objects.create(
            client=client,
            total_amount=Decimal('1000.00'),
            service_description='Test service',
            status='pending'
        )
        
        initial_count = AuditLog.objects.count()
        
        # Update payment
        payment.status = 'paid'
        payment.amount_paid = Decimal('1000.00')
        payment.save()
        
        # Check that UPDATE log was created with changes
        update_logs = AuditLog.objects.filter(
            action=AuditLog.Action.UPDATE,
            timestamp__gt=payment.created_at
        )
        
        self.assertGreater(update_logs.count(), 0)
        
        log = update_logs.latest('timestamp')
        if log.changes:
            # Changes should contain status update
            self.assertTrue('status' in log.changes or 'amount_paid' in log.changes)


class AuthenticationSignalsTest(TestCase):
    """Test authentication-related signals."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.factory = RequestFactory()
    
    def test_login_signal(self):
        """Test that successful login creates an audit log."""
        initial_count = AuditLog.objects.count()
        
        # Simulate login
        from django.contrib.auth.signals import user_logged_in
        request = self.factory.post('/login/')
        user_logged_in.send(sender=User, request=request, user=self.user)
        
        # Check that a LOGIN log was created
        self.assertEqual(AuditLog.objects.count(), initial_count + 1)
        
        log = AuditLog.objects.latest('timestamp')
        self.assertEqual(log.action, AuditLog.Action.LOGIN)
        self.assertEqual(log.user, self.user)
    
    def test_logout_signal(self):
        """Test that logout creates an audit log."""
        initial_count = AuditLog.objects.count()
        
        # Simulate logout
        from django.contrib.auth.signals import user_logged_out
        request = self.factory.post('/logout/')
        user_logged_out.send(sender=User, request=request, user=self.user)
        
        # Check that a LOGOUT log was created
        self.assertEqual(AuditLog.objects.count(), initial_count + 1)
        
        log = AuditLog.objects.latest('timestamp')
        self.assertEqual(log.action, AuditLog.Action.LOGOUT)
        self.assertEqual(log.user, self.user)
    
    def test_login_failed_signal(self):
        """Test that failed login attempts are logged."""
        initial_count = AuditLog.objects.count()
        
        # Simulate failed login
        from django.contrib.auth.signals import user_login_failed
        request = self.factory.post('/login/')
        credentials = {'username': 'wronguser'}
        user_login_failed.send(
            sender=User,
            credentials=credentials,
            request=request
        )
        
        # Check that a LOGIN_FAILED log was created
        self.assertEqual(AuditLog.objects.count(), initial_count + 1)
        
        log = AuditLog.objects.latest('timestamp')
        self.assertEqual(log.action, AuditLog.Action.LOGIN_FAILED)
        self.assertIn('wronguser', log.description)
