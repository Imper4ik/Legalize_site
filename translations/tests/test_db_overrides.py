from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.utils import ProgrammingError
from django.urls import reverse
from unittest.mock import patch

from translations.models import RuntimeTranslation
from translations.utils import load_all_translations, save_translation_entry
from translations.runtime import apply_db_override, clear_translation_override_cache

User = get_user_model()

@pytest.mark.django_db
class TestTranslationOverrides:

    def setup_method(self):
        cache.clear()
        # Ensure we have clean state
        RuntimeTranslation.objects.all().delete()

    def test_model_uniqueness(self):
        """RuntimeTranslation should be unique per msgid and language_code."""
        RuntimeTranslation.objects.create(msgid="Hello", language_code="ru", msgstr="Привет")
        
        with pytest.raises(Exception): # IntegrityError or similar depending on DB
            RuntimeTranslation.objects.create(msgid="Hello", language_code="ru", msgstr="Здравствуй")

    def test_inactive_override_not_applied(self):
        """Inactive overrides should not be returned by runtime."""
        RuntimeTranslation.objects.create(msgid="Hello", language_code="ru", msgstr="Привет", is_active=False)
        
        translated = apply_db_override("Hello", "Original", "ru")
        assert translated == "Original"

    def test_active_override_applied(self):
        """Active overrides should be returned by runtime."""
        RuntimeTranslation.objects.create(msgid="Hello", language_code="ru", msgstr="Привет", is_active=True)
        
        translated = apply_db_override("Hello", "Original", "ru")
        assert translated == "Привет"

    def test_cache_usage_and_clear(self):
        """Runtime should use cache and clear it on update."""
        RuntimeTranslation.objects.create(msgid="Hello", language_code="ru", msgstr="Привет", is_active=True)
        
        # First call hits DB
        translated = apply_db_override("Hello", "Original", "ru")
        assert translated == "Привет"
        
        # Update DB directly without clearing cache
        RuntimeTranslation.objects.filter(msgid="Hello", language_code="ru").update(msgstr="Здравствуй")
        
        # Second call should still return cached value
        translated = apply_db_override("Hello", "Original", "ru")
        assert translated == "Привет"
        
        # Clear cache
        clear_translation_override_cache("Hello", "ru")
        
        # Third call should hit DB and return new value
        translated = apply_db_override("Hello", "Original", "ru")
        assert translated == "Здравствуй"

    def test_fallback_when_db_missing(self):
        """App should not crash if DB table is missing."""
        with patch('translations.models.RuntimeTranslation.objects.filter') as mock_filter:
            mock_filter.side_effect = ProgrammingError("Table does not exist")
            
            # Should not raise exception
            translated = apply_db_override("Hello", "Original", "ru")
            assert translated == "Original"

    def test_utils_save_to_db(self):
        """save_translation_entry should save to DB when storage=database."""
        save_translation_entry("Hello", ru="Привет", storage="database")
        
        override = RuntimeTranslation.objects.filter(msgid="Hello", language_code="ru").first()
        assert override is not None
        assert override.msgstr == "Привет"

    def test_utils_load_overlays_db(self):
        """load_all_translations should overlay DB on top of PO."""
        RuntimeTranslation.objects.create(msgid="Clients", language_code="ru", msgstr="Клиенты из БД", is_active=True)
        
        all_trans = load_all_translations()
        
        # Find the entry for 'Clients'
        entry = next((e for e in all_trans if e['msgid'] == 'Clients'), None)
        assert entry is not None
        assert entry['ru'] == "Клиенты из БД"
        assert entry['source_ru'] == "db"

    def test_view_permissions(self, client):
        """Only superuser/Admin/Translator can access update API."""
        url = reverse('translations:update_api')
        
        # Anonymous
        response = client.post(url, {'msgid': 'Hello', 'ru': 'Привет'}, content_type='application/json')
        assert response.status_code == 302 # Redirect to login
        
        # Normal user
        user = User.objects.create_user(email='user@example.test', password='password', is_staff=True)
        client.force_login(user)
        response = client.post(url, {'msgid': 'Hello', 'ru': 'Привет'}, content_type='application/json')
        assert response.status_code == 302 # Redirect (denied)
        
        # Admin role
        from django.contrib.auth.models import Group
        from clients.services.roles import ensure_predefined_roles
        ensure_predefined_roles()
        admin_group = Group.objects.get(name="Admin")
        user.groups.add(admin_group)
        response = client.post(url, {'msgid': 'Hello', 'ru': 'Привет'}, content_type='application/json')
        assert response.status_code == 200
        assert response.json()['status'] == 'ok'

    def test_commands(self):
        """Test import/export commands."""
        from django.core.management import call_command
        import os
        
        # Import dry-run
        call_command('import_po_to_db', '--dry-run')
        assert RuntimeTranslation.objects.count() == 0
        
        # Export dry-run
        RuntimeTranslation.objects.create(msgid="Hello", language_code="ru", msgstr="Привет", is_active=True)
        call_command('export_db_translations_to_po', '--dry-run')
