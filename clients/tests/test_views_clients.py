from django.test import TestCase, Client as DjangoClient
from django.urls import reverse
from django.contrib.auth import get_user_model

from clients.models import Client, Payment, Document, Reminder
from clients.forms import ClientForm

User = get_user_model()


class ClientViewsTests(TestCase):
    def setUp(self):
        # Create staff user
        self.staff_user = User.objects.create_superuser(
            username="staff_admin", email="staff@example.com", password="password123"
        )
        # Create regular user
        self.regular_user = User.objects.create_user(
            username="regular_user", email="user@example.com", password="password123"
        )
        # Create a client object
        self.client_obj = Client.objects.create(
            first_name="Ivan",
            last_name="Ivanov",
            email="ivan@example.com",
            phone="123456789",
        )
        
        self.client_with_user = Client.objects.create(
            first_name="Petr",
            last_name="Petrov",
            email="user@example.com",
            user=self.regular_user
        )

        self.client = DjangoClient()

    def test_client_list_view_staff(self):
        self.client.login(email="staff@example.com", password="password123")
        response = self.client.get(reverse('clients:client_list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.client_obj, response.context['clients'])
        self.assertIn(self.client_with_user, response.context['clients'])
        self.assertTemplateUsed(response, 'clients/clients_list.html')
        
    def test_client_list_view_search(self):
        self.client.login(email="staff@example.com", password="password123")
        response = self.client.get(reverse('clients:client_list'), {'q': 'Ivan'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.client_obj, response.context['clients'])
        self.assertNotIn(self.client_with_user, response.context['clients'])

    def test_client_list_view_regular_user(self):
        self.client.login(email="user@example.com", password="password123")
        response = self.client.get(reverse('clients:client_list'))
        # Should redirect to login or 403 due to StaffRequiredMixin
        self.assertEqual(response.status_code, 403)

    def test_client_detail_view(self):
        self.client.login(email="staff@example.com", password="password123")
        response = self.client.get(reverse('clients:client_detail', kwargs={'pk': self.client_obj.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['client'], self.client_obj)
        self.assertTemplateUsed(response, 'clients/client_detail.html')

    def test_client_create_view(self):
        self.client.login(email="staff@example.com", password="password123")
        data = {
            'first_name': 'New',
            'last_name': 'Client',
            'email': 'new@example.com',
            'phone': '987654321',
            'sex': 'm',
            'citizenship': 'UA',
            'passport_num': 'XX123456',
            'language': 'pl',
            'is_student': False,
            'status': 'new',
            'application_purpose': 'work',
        }
        response = self.client.post(reverse('clients:client_add'), data=data)
        self.assertRedirects(response, reverse('clients:client_list'))
        self.assertEqual(Client.objects.filter(email='new@example.com').count(), 1)
        


    def test_client_update_view(self):
        self.client.login(email="staff@example.com", password="password123")
        data = {
            'first_name': 'Updated',
            'last_name': 'Ivanov',
            'email': 'ivan@example.com',
            'phone': '123456789',
            'language': 'en',
            'status': 'new',
            'citizenship': 'UA',
            'passport_num': 'XX123456',
            'is_student': False,
            'application_purpose': 'work',
        }
        response = self.client.post(reverse('clients:client_edit', kwargs={'pk': self.client_obj.pk}), data=data)
        self.assertRedirects(response, reverse('clients:client_detail', kwargs={'pk': self.client_obj.pk}))
        self.client_obj.refresh_from_db()
        self.assertEqual(self.client_obj.first_name, 'Updated')
        self.assertEqual(self.client_obj.language, 'en')

    def test_client_delete_view(self):
        self.client.login(email="staff@example.com", password="password123")
        response = self.client.post(reverse('clients:client_delete', kwargs={'pk': self.client_obj.pk}))
        self.assertRedirects(response, reverse('clients:client_list'))
        self.assertEqual(Client.objects.filter(pk=self.client_obj.pk).count(), 0)

    def test_dashboard_redirect_staff(self):
        self.client.login(email="staff@example.com", password="password123")
        response = self.client.get(reverse('root_dashboard'))
        self.assertRedirects(response, reverse('clients:client_list'))

    def test_dashboard_redirect_client(self):
        self.client.login(email="user@example.com", password="password123")
        response = self.client.get(reverse('root_dashboard'))
        # Should redirect to their profile or 403 (for now it returns 403 as per code if not staff)
        self.assertEqual(response.status_code, 403)
        
    def test_dashboard_redirect_anonymous(self):
        response = self.client.get(reverse('root_dashboard'))
        self.assertEqual(response.status_code, 302)
