from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from clients.models import Client

User = get_user_model()

class ClientAutocompleteTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="staff_user", email="staff@example.com", password="password", is_staff=True
        )
        from django.contrib.auth.models import Group
        staff_group, _ = Group.objects.get_or_create(name="Staff")
        self.staff_user.groups.add(staff_group)

        self.client_user = User.objects.create_user(
            username="client_user", email="client@example.com", password="password", is_staff=False
        )

        self.client_a = Client.objects.create(
            first_name="Alexander",
            last_name="Pushkin",
            email="alexander@example.com",
            phone="+48111111111",
        )
        self.client_b = Client.objects.create(
            first_name="Nikolai",
            last_name="Gogol",
            email="nikolai@example.com",
            phone="+48222222222",
        )

    def test_anonymous_user_blocked(self):
        url = reverse("clients:client_autocomplete_api")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)  # Redirects to login

    def test_regular_client_blocked(self):
        self.client.login(email="client@example.com", password="password")
        url = reverse("clients:client_autocomplete_api")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_autocomplete_returns_suggestions(self):
        self.client.login(email="staff@example.com", password="password")
        url = reverse("clients:client_autocomplete_api")

        # Test query too short
        response = self.client.get(url, {"q": "a"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"results": []})

        # Test query matches Alexander
        response = self.client.get(url, {"q": "Alex"})
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["first_name"], "Alexander")
        self.assertEqual(results[0]["last_name"], "Pushkin")
        self.assertEqual(results[0]["email"], "alexander@example.com")
        self.assertEqual(results[0]["phone"], "+48111111111")
        self.assertEqual(results[0]["url"], reverse("clients:client_detail", kwargs={"pk": self.client_a.id}))
