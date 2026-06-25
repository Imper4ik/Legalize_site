from datetime import date

from django.test import TestCase

from clients.forms import ClientDocumentRequirementForm, PaymentForm
from clients.models import Client, Case, Payment, ClientDocumentRequirement


class FormsIntegrityTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client.objects.create(
            first_name="Test",
            last_name="Client",
            email="test@example.com",
            phone="+48123123123",
            citizenship="UA",
            application_purpose="work",
            language="pl",
        )
        self.case = Case.objects.create(
            client=self.client,
            application_purpose="work",
            workflow_stage="new_client",
        )

    def test_payment_form_meta_and_validation(self):
        payment = Payment(client=self.client, case=self.case)
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
            instance=payment,
        )
        self.assertIn("service_description", form.fields)
        self.assertTrue(form.is_valid(), form.errors)

    def test_client_document_requirement_form_fields(self):
        req = ClientDocumentRequirement(client=self.client, case=self.case)
        form = ClientDocumentRequirementForm(
            data={"name": "  A  ", "description": "x", "is_required": True},
            instance=req,
        )
        self.assertEqual(set(form.fields.keys()), {"name", "description", "is_required", "due_date"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["name"], "A")
