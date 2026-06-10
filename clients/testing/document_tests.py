from __future__ import annotations

from django.test import Client as DjangoClient
from django.urls import reverse

from clients.constants import DocumentType
from clients.testing.assertions import RelatedObjects, ScenarioRecorder
from clients.testing.factories import (
    create_client_user,
    create_test_client,
    create_test_document,
    create_test_user,
)


def run_document_access_scenarios(recorder: ScenarioRecorder) -> None:
    staff_1 = create_test_user(role="Staff", email="test-center-staff-1@example.test")
    staff_2 = create_test_user(role="Staff", email="test-center-staff-2@example.test")
    client_1 = create_test_client(
        email="client_access_1@example.test",
        assigned_staff=staff_1,
        first_name="Access",
        last_name="One",
    )
    client_2 = create_test_client(
        email="client_access_2@example.test",
        assigned_staff=staff_2,
        first_name="Access",
        last_name="Two",
    )
    doc_1 = create_test_document(client_1, doc_type=DocumentType.PASSPORT.value, filename="client-1.pdf")
    doc_2 = create_test_document(client_2, doc_type=DocumentType.PASSPORT.value, filename="client-2.pdf")

    browser = DjangoClient()
    browser.force_login(staff_1)
    own_response = browser.get(reverse("clients:document_download", kwargs={"doc_id": doc_1.pk}))
    recorder.check(
        "documents.staff_can_download_assigned_client_document",
        own_response.status_code < 400,
        expected="status < 400",
        actual=f"status={own_response.status_code}",
        related=RelatedObjects(client=client_1, document=doc_1),
    )

    foreign_response = browser.get(reverse("clients:document_download", kwargs={"doc_id": doc_2.pk}))
    recorder.check(
        "documents.staff_cannot_download_unassigned_client_document",
        foreign_response.status_code in {403, 404},
        expected="403 or 404",
        actual=f"status={foreign_response.status_code}",
        related=RelatedObjects(client=client_2, document=doc_2),
    )

    client_user = create_client_user(email="test-center-client-user@example.test")
    client_1.user = client_user
    client_1.save(update_fields=["user"])
    browser.force_login(client_user)
    client_direct_response = browser.get(reverse("clients:document_download", kwargs={"doc_id": doc_2.pk}))
    recorder.check(
        "documents.client_cannot_download_foreign_document_direct_url",
        client_direct_response.status_code in {403, 404},
        expected="403 or 404",
        actual=f"status={client_direct_response.status_code}",
        related=RelatedObjects(client=client_2, document=doc_2),
    )

    staff_panel_response = browser.get(reverse("clients:admin_panel"))
    recorder.check(
        "permissions.client_cannot_open_staff_panel",
        staff_panel_response.status_code in {302, 403},
        expected="redirect or forbidden",
        actual=f"status={staff_panel_response.status_code}",
        related=RelatedObjects(client=client_1),
    )

