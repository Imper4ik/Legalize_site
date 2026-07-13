from __future__ import annotations

from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

from clients.models import Client, Document
from clients.services.cases import create_case_for_client
from clients.testing.factories import (
    TEST_USER_CREDENTIAL,
    create_test_document,
    create_test_user,
)


def _valid_pdf_upload(name: str = "upload.pdf") -> SimpleUploadedFile:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, "case upload test")
    pdf.save()
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/pdf")


@pytest.mark.django_db
def test_case_detail_renders_with_ux_changes(client):
    staff = create_test_user(role="Manager")
    client.login(email=staff.email, password=TEST_USER_CREDENTIAL)

    customer = Client.objects.create(first_name="Darya", last_name="A", citizenship="BY")
    case = create_case_for_client(client=customer, actor=staff)

    response = client.get(reverse("clients:case_detail", kwargs={"pk": case.pk}))
    body = response.content.decode()

    assert response.status_code == 200
    # Internal/unwanted fields are gone.
    assert "Версия записи" not in body
    assert "Ответственный" not in body
    # New UX affordances are present.
    assert reverse("clients:add_task", kwargs={"client_id": customer.pk}) in body
    assert reverse("clients:add_payment", kwargs={"client_id": customer.pk}) in body
    assert 'id="historyFilter"' in body
    # Documents are shown as a checklist grouped by requirement.
    assert 'id="documentChecklist"' in body
    # Working modals are present on the case page.
    assert 'id="caseAddTaskModal"' in body
    assert 'id="caseAddPaymentModal"' in body


@pytest.mark.django_db
def test_documents_shown_as_checklist_grouped_by_requirement(client):
    staff = create_test_user(role="Manager")
    client.login(email=staff.email, password=TEST_USER_CREDENTIAL)

    customer = Client.objects.create(first_name="Darya", last_name="A", citizenship="BY")
    case = create_case_for_client(client=customer, actor=staff)
    for _ in range(3):
        create_test_document(client=customer, doc_type="passport", case=case)

    response = client.get(reverse("clients:case_detail", kwargs={"pk": case.pk}))
    body = response.content.decode()

    assert response.status_code == 200
    # Checklist accordion (grouped by requirement), not a flat per-file list.
    assert 'id="documentChecklist"' in body


@pytest.mark.django_db
def test_add_payment_returns_to_case_via_next(client):
    staff = create_test_user(role="Manager")
    client.login(email=staff.email, password=TEST_USER_CREDENTIAL)

    customer = Client.objects.create(first_name="Darya", last_name="A", citizenship="BY")
    case = create_case_for_client(client=customer, actor=staff)
    case_url = reverse("clients:case_detail", kwargs={"pk": case.pk})

    response = client.post(
        reverse("clients:add_payment", kwargs={"client_id": customer.pk}),
        data={
            "service_description": "consultation",
            "total_amount": "100.00",
            "amount_paid": "0",
            "status": "pending",
            "payment_method": "cash",
            "next": case_url,
        },
    )

    assert response.status_code == 302
    assert response.url == case_url


@pytest.mark.django_db
def test_case_detail_shows_document_add_and_delete_controls(client):
    staff = create_test_user(role="Staff")
    client.login(email=staff.email, password=TEST_USER_CREDENTIAL)

    customer = Client.objects.create(first_name="Darya", last_name="A", citizenship="BY")
    case = create_case_for_client(client=customer, actor=staff)
    doc = create_test_document(client=customer, doc_type="passport", case=case)

    response = client.get(reverse("clients:case_detail", kwargs={"pk": case.pk}))
    body = response.content.decode()

    assert response.status_code == 200
    # Upload form posts to add_document for this case.
    assert reverse("clients:add_document", kwargs={"client_id": customer.pk, "doc_type": "passport"}) in body
    # Delete control is present for a Staff user (who can now delete documents).
    assert reverse("clients:document_delete", kwargs={"pk": doc.id}) in body


@pytest.mark.django_db
def test_case_detail_shows_verify_control(client):
    staff = create_test_user(role="Staff")
    client.login(email=staff.email, password=TEST_USER_CREDENTIAL)

    customer = Client.objects.create(first_name="Darya", last_name="A", citizenship="BY")
    case = create_case_for_client(client=customer, actor=staff)
    doc = create_test_document(client=customer, doc_type="passport", case=case)

    response = client.get(reverse("clients:case_detail", kwargs={"pk": case.pk}))
    body = response.content.decode()

    assert response.status_code == 200
    assert reverse("clients:toggle_document_verification", kwargs={"doc_id": doc.id}) in body


@pytest.mark.django_db
def test_verify_document_returns_to_case_via_next(client):
    staff = create_test_user(role="Staff")
    client.login(email=staff.email, password=TEST_USER_CREDENTIAL)

    customer = Client.objects.create(first_name="Darya", last_name="A", citizenship="BY")
    case = create_case_for_client(client=customer, actor=staff)
    doc = create_test_document(client=customer, doc_type="passport", case=case, verified=False)
    case_url = reverse("clients:case_detail", kwargs={"pk": case.pk})

    response = client.post(
        reverse("clients:toggle_document_verification", kwargs={"doc_id": doc.id}),
        data={"next": f"{case_url}#documents"},
    )

    assert response.status_code == 302
    assert response.url == f"{case_url}#documents"
    doc.refresh_from_db()
    assert doc.verified is True


@pytest.mark.django_db
def test_add_document_returns_to_case_via_next(client):
    staff = create_test_user(role="Staff")
    client.login(email=staff.email, password=TEST_USER_CREDENTIAL)

    customer = Client.objects.create(first_name="Darya", last_name="A", citizenship="BY")
    case = create_case_for_client(client=customer, actor=staff)
    case_url = reverse("clients:case_detail", kwargs={"pk": case.pk})

    response = client.post(
        reverse("clients:add_document", kwargs={"client_id": customer.pk, "doc_type": "passport"}),
        data={
            "file": _valid_pdf_upload("passport-upload.pdf"),
            "case_uuid": str(case.uuid),
            "next": case_url,
        },
    )

    assert response.status_code == 302
    assert response.url == case_url
    assert Document.objects.filter(client=customer, document_type="passport").exists()


@pytest.mark.django_db
def test_staff_delete_document_returns_to_case_via_next(client):
    staff = create_test_user(role="Staff")
    client.login(email=staff.email, password=TEST_USER_CREDENTIAL)

    customer = Client.objects.create(first_name="Darya", last_name="A", citizenship="BY")
    case = create_case_for_client(client=customer, actor=staff)
    doc = create_test_document(client=customer, doc_type="passport", case=case)
    case_url = reverse("clients:case_detail", kwargs={"pk": case.pk})

    response = client.post(
        reverse("clients:document_delete", kwargs={"pk": doc.id}),
        data={"next": case_url},
    )

    assert response.status_code == 302
    assert response.url == case_url
    assert not Document.objects.filter(pk=doc.id).exists()


@pytest.mark.django_db
def test_document_delete_rejects_offsite_next(client):
    staff = create_test_user(role="Staff")
    client.login(email=staff.email, password=TEST_USER_CREDENTIAL)

    customer = Client.objects.create(first_name="Darya", last_name="A", citizenship="BY")
    case = create_case_for_client(client=customer, actor=staff)
    doc = create_test_document(client=customer, doc_type="passport", case=case)

    response = client.post(
        reverse("clients:document_delete", kwargs={"pk": doc.id}),
        data={"next": "https://evil.example.com/phish"},
    )

    assert response.status_code == 302
    assert "evil.example.com" not in response.url


@pytest.mark.django_db
def test_add_payment_rejects_offsite_next(client):
    staff = create_test_user(role="Manager")
    client.login(email=staff.email, password=TEST_USER_CREDENTIAL)
    customer = Client.objects.create(first_name="Darya", last_name="A", citizenship="BY")
    create_case_for_client(client=customer, actor=staff)

    response = client.post(
        reverse("clients:add_payment", kwargs={"client_id": customer.pk}),
        data={
            "service_description": "consultation",
            "total_amount": "100.00",
            "amount_paid": "0",
            "status": "pending",
            "payment_method": "cash",
            "next": "https://evil.example.com/phish",
        },
    )

    assert response.status_code == 302
    # Open-redirect is rejected; falls back to the client page.
    assert "evil.example.com" not in response.url
