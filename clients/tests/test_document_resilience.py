import pytest
import logging
import zipfile
from django.urls import reverse
from django.core.files.base import ContentFile
from django.contrib.messages import get_messages
from clients.models import Document

@pytest.fixture
def sample_document(sample_client):
    doc = Document.objects.create(
        client=sample_client,
        document_type="passport"
    )
    doc.file.save("test_passport.pdf", ContentFile(b"fake pdf content"))
    return doc

@pytest.mark.django_db
def test_document_download_existing_file(logged_in_staff, sample_document):
    """Task 6.1: document_download existing file returns 200 and records activity."""
    url = reverse("clients:document_download", kwargs={"doc_id": sample_document.pk})
    response = logged_in_staff.get(url)
    assert response.status_code == 200
    assert sample_document.client.activities.filter(event_type="document_downloaded").exists()

@pytest.mark.django_db
def test_document_download_missing_physical_file(logged_in_staff, sample_document, caplog):
    """Task 6.2: document_download missing physical file redirects and logs warning."""
    # Delete the physical file from storage but keep the DB record
    sample_document.file.storage.delete(sample_document.file.name)
    
    url = reverse("clients:document_download", kwargs={"doc_id": sample_document.pk})
    with caplog.at_level(logging.WARNING):
        response = logged_in_staff.get(url)
    
    assert response.status_code == 302
    assert response.url == reverse("clients:client_detail", kwargs={"pk": sample_document.client.pk})
    
    messages = list(get_messages(response.wsgi_request))
    assert any("Файл отсутствует в хранилище" in str(m) for m in messages)
    assert "Physical file missing in storage" in caplog.text

@pytest.mark.django_db
def test_unauthorized_document_download(client, sample_document):
    """Task 6.3: unauthorized document download returns 404 (via accessible_documents_queryset)."""
    # Anonymous client
    url = reverse("clients:document_download", kwargs={"doc_id": sample_document.pk})
    response = client.get(url)
    # accessible_documents_queryset filter will result in 404 for anonymous users or non-staff
    assert response.status_code in [404, 302]

@pytest.mark.django_db
def test_zip_export_with_missing_file(sample_client, sample_document):
    """Task 6.4: ZIP export handles missing files and includes MISSING_FILES.txt."""
    sample_document.file.storage.delete(sample_document.file.name)
    
    from clients.services.export import generate_client_zip
    
    buffer = generate_client_zip(sample_client)
    with zipfile.ZipFile(buffer) as zf:
        file_list = zf.namelist()
        missing_report_files = [f for f in file_list if "MISSING_FILES.txt" in f]
        assert len(missing_report_files) > 0
        content = zf.read(missing_report_files[0]).decode()
        assert f"ID={sample_document.pk}" in content

@pytest.mark.django_db
def test_document_version_archive_copies_file_physically(sample_document):
    """Task 6.5: document version archive copies file physically."""
    from clients.services.document_versions import archive_document_version
    
    original_content = b"original content"
    sample_document.file.save("original.txt", ContentFile(original_content))
    
    version = archive_document_version(sample_document)
    assert version is not None
    assert version.file.name != sample_document.file.name
    
    # Verify content in version
    version.file.open("rb")
    assert version.file.read() == original_content
    version.file.close()
    
    # Replace current document file
    sample_document.file.save("new.txt", ContentFile(b"new content"))
    
    # Verify version STILL has original content
    version.file.open("rb")
    assert version.file.read() == original_content
    version.file.close()
    
    # Even if we delete the current document file
    sample_document.file.storage.delete(sample_document.file.name)
    
    version.file.open("rb")
    assert version.file.read() == original_content
    version.file.close()
