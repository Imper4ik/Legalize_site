"""
Tests for AuditLog model and functionality.
"""
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from clients.models import Client, Document, Payment
from core.models import AuditLog

User = get_user_model()


class AuditLogModelTest(TestCase):
    """Test AuditLog model methods."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.factory = RequestFactory()
    
    def test_audit_log_creation(self):
        """Test creating an audit log entry."""
        log = AuditLog.objects.create(
            user=self.user,
            username=self.user.username,
            action=AuditLog.Action.CREATE,
            description='Test log entry',
        )
        
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.action, AuditLog.Action.CREATE)
        self.assertEqual(log.description, 'Test log entry')
    
    def test_log_action_method(self):
        """Test the log_action class method."""
        client = Client.objects.create(
            first_name='Иван',
            last_name='Петров',
            email='ivan@example.com',
            phone='+48123456789',
            citizenship='RU',
            application_purpose='work'
        )
        
        request = self.factory.get('/test/')
        request.user = self.user
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        request.META['HTTP_USER_AGENT'] = 'Mozilla/5.0'
        
        log = AuditLog.log_action(
            action=AuditLog.Action.CREATE,
            user=self.user,
            obj=client,
            changes={'status': {'old': None, 'new': 'new'}},
            description='Client created',
            request=request
        )
        
        self.assertIsNotNone(log)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.action, AuditLog.Action.CREATE)
        self.assertEqual(log.object_repr, str(client))
        self.assertIsNotNone(log.changes)
        self.assertEqual(log.ip_address, '127.0.0.1')
        self.assertEqual(log.user_agent, 'Mozilla/5.0')
    
    def test_log_string_representation(self):
        """Test __str__ method."""
        client = Client.objects.create(
            first_name='Иван',
            last_name='Петров',
            email='ivan@example.com',
            phone='+48123456789',
            citizenship='RU',
            application_purpose='work'
        )
        
        log = AuditLog.log_action(
            action=AuditLog.Action.UPDATE,
            user=self.user,
            obj=client,
            description='Client updated'
        )
        
        str_repr = str(log)
        self.assertIn('testuser', str_repr)
        self.assertIn('Обновление', str_repr)  # Russian translation of UPDATE
        self.assertIn('client', str_repr.lower())
    
    def test_get_changes_display(self):
        """Test formatted changes display."""
        changes = {
            'first_name': {'old': 'Иван', 'new': 'Петр'},
            'status': {'old': 'new', 'new': 'active'}
        }
        
        log = AuditLog.objects.create(
            user=self.user,
            username=self.user.username,
            action=AuditLog.Action.UPDATE,
            changes=changes
        )
        
        formatted = log.get_changes_display()
        self.assertIn('first_name', formatted)
        self.assertIn('Иван', formatted)
        self.assertIn('Петр', formatted)


class AuditLogFilteringTest(TestCase):
    """Test filtering and querying audit logs."""
    
    def setUp(self):
        """Create test data."""
        self.user1 = User.objects.create_user(username='user1', email='user1@test.com')
        self.user2 = User.objects.create_user(username='user2', email='user2@test.com')
    
    def test_filter_by_user(self):
        """Test filtering logs by user."""
        AuditLog.objects.create(
            user=self.user1,
            username=self.user1.username,
            action=AuditLog.Action.LOGIN
        )
        AuditLog.objects.create(
            user=self.user1,
            username=self.user1.username,
            action=AuditLog.Action.CREATE
        )
        AuditLog.objects.create(
            user=self.user2,
            username=self.user2.username,
            action=AuditLog.Action.LOGIN
        )
        
        user1_logs = AuditLog.objects.filter(user=self.user1)
        self.assertEqual(user1_logs.count(), 2)
        
        user2_logs = AuditLog.objects.filter(user=self.user2)
        self.assertEqual(user2_logs.count(), 1)
    
    def test_filter_by_action(self):
        """Test filtering logs by action type."""
        AuditLog.objects.create(
            user=self.user1,
            username=self.user1.username,
            action=AuditLog.Action.CREATE
        )
        AuditLog.objects.create(
            user=self.user1,
            username=self.user1.username,
            action=AuditLog.Action.UPDATE
        )
        AuditLog.objects.create(
            user=self.user1,
            username=self.user1.username,
            action=AuditLog.Action.DELETE
        )
        
        create_logs = AuditLog.objects.filter(action=AuditLog.Action.CREATE)
        self.assertEqual(create_logs.count(), 1)
        
        update_logs = AuditLog.objects.filter(action=AuditLog.Action.UPDATE)
        self.assertEqual(update_logs.count(), 1)
    
    def test_ordering(self):
        """Test that logs are ordered by timestamp descending."""
        log1 = AuditLog.objects.create(
            user=self.user1,
            username=self.user1.username,
            action=AuditLog.Action.CREATE
        )
        log2 = AuditLog.objects.create(
            user=self.user1,
            username=self.user1.username,
            action=AuditLog.Action.UPDATE
        )
        log3 = AuditLog.objects.create(
            user=self.user1,
            username=self.user1.username,
            action=AuditLog.Action.DELETE
        )
        
        logs = list(AuditLog.objects.all())
        # Most recent first
        self.assertEqual(logs[0].pk, log3.pk)
        self.assertEqual(logs[1].pk, log2.pk)
        self.assertEqual(logs[2].pk, log1.pk)
