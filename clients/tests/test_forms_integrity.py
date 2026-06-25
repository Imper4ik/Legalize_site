from datetime import date

from django.test import TestCase

from clients.forms import ClientDocumentRequirementForm, PaymentForm
from clients.testing.factories import create_test_client


class FormsIntegrityTests(TestCase):
    def setUp(self):
        # Case-first forms need a client so the model can resolve the case of a
        # single-case client during validation (spec section 5).
        self.client_obj = create_test_client()

    def test_payment_form_meta_and_validation(self):
        form = PaymentForm(
            data={
                "service_description": "consultation",
                "total_amount": "100.00",
                "amount_paid": "0.00",
                "status": "pending",
                "payment_method": "cash",
                "payment_date": date.today().isoformat(),
                "due_date": date.today().isoformat(),
                "transaction_id": "tx1",
            },
            client=self.client_obj,
        )
        self.assertIn("service_description", form.fields)
        self.assertTrue(form.is_valid(), form.errors)

    def test_client_document_requirement_form_fields(self):
        form = ClientDocumentRequirementForm(
            data={"name": "  A  ", "description": "x", "is_required": True},
            client=self.client_obj,
        )
        self.assertEqual(set(form.fields.keys()), {"name", "description", "is_required", "due_date"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["name"], "A")
