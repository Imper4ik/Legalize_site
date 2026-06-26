from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as DjangoClient
from django.urls import reverse

from clients.constants import DocumentType
from clients.models import Document
from clients.testing.assertions import RelatedObjects, ScenarioRecorder
from clients.testing.factories import (
    create_client_user,
    create_test_client,
    create_test_document,
    create_test_user,
)


def run_document_access_scenarios(recorder: ScenarioRecorder) -> None:
    staff_1 = create_test_user(role="Staff", email="test-center-staff-1@example.test")
    client_1 = create_test_client(
        email="client_access_1@example.test",
        first_name="Access",
        last_name="One",
    )
    client_2 = create_test_client(
        email="client_access_2@example.test",
        first_name="Access",
        last_name="Two",
    )
    doc_1 = create_test_document(client_1, doc_type=DocumentType.PASSPORT.value, filename="client-1.pdf")
    doc_2 = create_test_document(client_2, doc_type=DocumentType.PASSPORT.value, filename="client-2.pdf")

    browser = DjangoClient()
    browser.force_login(staff_1)
    own_response = browser.get(reverse("clients:document_download", kwargs={"doc_id": doc_1.pk}))
    recorder.check(
        "documents.staff_can_download_any_client_document",
        own_response.status_code < 400,
        expected="status < 400",
        actual=f"status={own_response.status_code}",
        related=RelatedObjects(client=client_1, document=doc_1),
    )

    # Every internal staff member has office-wide access: there is no per-staff
    # client assignment, so staff_1 can also reach another client's document
    # (spec §2).
    foreign_response = browser.get(reverse("clients:document_download", kwargs={"doc_id": doc_2.pk}))
    recorder.check(
        "documents.staff_can_download_other_client_document",
        foreign_response.status_code < 400,
        expected="status < 400",
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

    # 1. Test previews (PDF/images)
    browser.force_login(staff_1)
    pdf_preview_resp = browser.get(reverse("clients:document_preview", kwargs={"doc_id": doc_1.pk}))
    recorder.check(
        "documents.staff_can_preview_pdf",
        pdf_preview_resp.status_code == 200,
        expected="200",
        actual=f"status={pdf_preview_resp.status_code}",
        related=RelatedObjects(client=client_1, document=doc_1),
    )

    # 2. Test invalid types (DOCX block, invalid/corrupt WEBP block)
    docx_file = SimpleUploadedFile("invalid.docx", b"docx body", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    invalid_upload_resp = browser.post(
        reverse("clients:add_document", kwargs={"client_id": client_1.pk, "doc_type": DocumentType.PASSPORT.value}),
        {"file": docx_file},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest"
    )
    recorder.check(
        "documents.docx_upload_blocked",
        invalid_upload_resp.status_code == 400 and invalid_upload_resp.json().get("status") == "error",
        expected="status 400 with error JSON",
        actual=f"status={invalid_upload_resp.status_code}, json={invalid_upload_resp.json() if invalid_upload_resp.status_code == 400 else ''}",
        related=RelatedObjects(client=client_1),
    )

    invalid_webp = SimpleUploadedFile("invalid.webp", b"corrupted bytes", content_type="image/webp")
    invalid_webp_resp = browser.post(
        reverse("clients:add_document", kwargs={"client_id": client_1.pk, "doc_type": DocumentType.PASSPORT.value}),
        {"file": invalid_webp},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest"
    )
    recorder.check(
        "documents.corrupted_webp_upload_blocked",
        invalid_webp_resp.status_code == 400 and invalid_webp_resp.json().get("status") == "error",
        expected="status 400 with error JSON",
        actual=f"status={invalid_webp_resp.status_code}, json={invalid_webp_resp.json() if invalid_webp_resp.status_code == 400 else ''}",
        related=RelatedObjects(client=client_1),
    )

    # 3. Test downloads (DOCX) - if a docx file is present in database
    doc_docx = Document.objects.create(
        client=client_1,
        document_type=DocumentType.PASSPORT.value,
        file=SimpleUploadedFile("manual.docx", b"docx contents", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        is_test_data=True,
    )
    docx_download_resp = browser.get(reverse("clients:document_download", kwargs={"doc_id": doc_docx.pk}))
    recorder.check(
        "documents.can_download_docx",
        docx_download_resp.status_code == 200,
        expected="200",
        actual=f"status={docx_download_resp.status_code}",
        related=RelatedObjects(client=client_1, document=doc_docx),
    )

    # 4. Cyrillic/Polish file encodings
    cyrillic_file = SimpleUploadedFile("załącznik_№1_паспорт.pdf", b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n", content_type="application/pdf")
    cyrillic_upload_resp = browser.post(
        reverse("clients:add_document", kwargs={"client_id": client_1.pk, "doc_type": DocumentType.PASSPORT.value}),
        {"file": cyrillic_file},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest"
    )
    recorder.check(
        "documents.cyrillic_and_polish_filename_uploaded",
        cyrillic_upload_resp.status_code == 200 and cyrillic_upload_resp.json().get("status") == "success",
        expected="status 200 with success JSON",
        actual=f"status={cyrillic_upload_resp.status_code}, json={cyrillic_upload_resp.json() if cyrillic_upload_resp.status_code == 200 else ''}",
        related=RelatedObjects(client=client_1),
    )

    if cyrillic_upload_resp.status_code == 200:
        uploaded_cyrillic_doc = Document.objects.get(pk=cyrillic_upload_resp.json().get("doc_id"))
        cyrillic_download_resp = browser.get(reverse("clients:document_download", kwargs={"doc_id": uploaded_cyrillic_doc.pk}))
        recorder.check(
            "documents.cyrillic_filename_downloaded",
            cyrillic_download_resp.status_code == 200,
            expected="200",
            actual=f"status={cyrillic_download_resp.status_code}",
            related=RelatedObjects(client=client_1, document=uploaded_cyrillic_doc),
        )

    # 5. Missing files handling
    doc_missing = Document.objects.create(
        client=client_1,
        document_type=DocumentType.PASSPORT.value,
        file=SimpleUploadedFile("missing.pdf", b"dummy"),
        is_test_data=True,
    )
    if doc_missing.file:
        doc_missing.file.storage.delete(doc_missing.file.name)

    missing_download_resp = browser.get(reverse("clients:document_download", kwargs={"doc_id": doc_missing.pk}))
    recorder.check(
        "documents.missing_physical_file_redirects",
        missing_download_resp.status_code == 302,
        expected="302 redirect",
        actual=f"status={missing_download_resp.status_code}",
        related=RelatedObjects(client=client_1, document=doc_missing),
    )

    # 6. Deleted files
    doc_to_delete = create_test_document(client_1, doc_type=DocumentType.PASSPORT.value, filename="to_delete.pdf")
    delete_resp = browser.post(reverse("clients:document_delete", kwargs={"pk": doc_to_delete.pk}))
    doc_to_delete.refresh_from_db()
    recorder.check(
        "documents.document_is_deleted_softly",
        delete_resp.status_code == 302 and doc_to_delete.archived_at is not None,
        expected="302 redirect and archived_at not null",
        actual=f"status={delete_resp.status_code}, archived_at={doc_to_delete.archived_at}",
        related=RelatedObjects(client=client_1, document=doc_to_delete),
    )

    # 7. Version overrides
    from clients.services.document_versions import archive_document_version, replace_document_file
    doc_versioned = create_test_document(client_1, doc_type=DocumentType.PASSPORT.value, filename="versioned.pdf")
    version = archive_document_version(doc_versioned, uploaded_by=staff_1, comment="V1 archive")

    recorder.check(
        "documents.version_archived",
        version is not None and version.version_number == 1 and doc_versioned.versions.count() == 1,
        expected="version created, version_number=1",
        actual=f"version={version.version_number if version else None}, count={doc_versioned.versions.count()}",
        related=RelatedObjects(client=client_1, document=doc_versioned),
    )

    new_file = SimpleUploadedFile("version2.pdf", b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n", content_type="application/pdf")
    replace_document_file(doc_versioned, uploaded_file=new_file)
    doc_versioned.refresh_from_db()
    recorder.check(
        "documents.file_replaced",
        "version2" in (doc_versioned.file.name or "") and doc_versioned.ocr_status == "skipped",
        expected="file name updated, status reset",
        actual=f"name={doc_versioned.file.name}, ocr={doc_versioned.ocr_status}",
        related=RelatedObjects(client=client_1, document=doc_versioned),
    )


