from django.test import TestCase
from django.template.loader import render_to_string
from clients.models import Client

class UploadModalDatasetTest(TestCase):
    def test_upload_modal_dataset_attributes(self):
        # We need a dummy client to pass to the template
        # The template expects 'client', 'CURRENT_LANGUAGE'

        # We can just render the modals.html template or use SimpleTestCase if we pass a mock.
        # Let's create a real client since we are in TestCase
        client = Client.objects.create(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            phone="123456789"
        )

        context = {
            'client': client,
            'CURRENT_LANGUAGE': 'ru',
            'service_choices': [],
            'payment_form': type('MockForm', (), {
                'status': type('MockField', (), {'field': type('MockInner', (), {'choices': []})()})(),
                'payment_method': type('MockField', (), {'field': type('MockInner', (), {'choices': []})()})(),
            })()
        }

        html = render_to_string('clients/partials/modals.html', context)

        # Check for dataset attributes in upload modal
        expected_attributes = [
            'data-upload-text',
            'data-upload-only-text',
            'data-upload-error-text',
            'data-file-too-large-text',
            'data-uploading-document-prefix',
            'data-upload-success-text',
            'data-session-expired-text'
        ]

        for attr in expected_attributes:
            self.assertIn(attr, html, f"Modal HTML is missing '{attr}' dataset attribute.")
