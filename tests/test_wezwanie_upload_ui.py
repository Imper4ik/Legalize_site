import pytest
from django.urls import reverse
from clients.models import Client
from clients.constants import DocumentType

@pytest.mark.django_db
def test_wezwanie_upload_button_present(admin_client):
    """
    Проверяет наличие кнопки загрузки Wezwanie в меню действий клиента.
    """
    client = Client.objects.create(
        first_name="Test",
        last_name="User",
        email="test@example.com",
        phone="+123456789"
    )
    
    url = reverse('clients:client_detail', kwargs={'pk': client.pk})
    response = admin_client.get(url)
    
    assert response.status_code == 200
    
    # Проверяем наличие кнопки с правильными атрибутами
    content = response.content.decode('utf-8')
    assert 'data-bs-target="#uploadDocumentModal"' in content
    assert 'data-doc-type="wezwanie"' in content
    # Проверяем текст кнопки (на русском или переведенный)
    assert "Загрузить Wezwanie" in content or "&#1047;&#1072;&#1075;&#1088;&#1091;&#1079;&#1080;&#1090;&#1100; Wezwanie" in content
