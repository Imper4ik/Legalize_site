"""UI smoke test for the Wezwanie upload button on the client detail page."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from clients.models import Client


class WezwanieUploadButtonTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username="admin_ui", password="pass", email="admin_ui@example.com"
        )
        self.client_profile = Client.objects.create(
            first_name="Test",
            last_name="User",
            email="ui_test@example.com",
            phone="+123456789",
            citizenship="UA",
        )

    def test_wezwanie_upload_button_present(self):
        """Check that the Wezwanie upload button appears in the client detail action menu."""
        self.client.force_login(self.admin)
        url = reverse("clients:client_detail", kwargs={"pk": self.client_profile.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn('data-bs-target="#uploadDocumentModal"', content)
        self.assertIn('data-doc-type="wezwanie"', content)
