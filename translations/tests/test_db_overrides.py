from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.utils import ProgrammingError
from django.urls import reverse
from unittest.mock import patch

from translations.models import TranslationOverride
from translations.utils import load_all_translations, save_translation_entry
from translations.runtime import apply_db_override, clear_translation_override_cache

User = get_user_model()

@pytest.mark.django_db
class TestTranslationOverrides:

    def setup_method(self):
        cache.clear()
        # Ensure we have clean state
        TranslationOverride.objects.all().delete()

    def test_model_uniqueness(self):
        """TranslationOverride should be unique per msgid and language."""
        TranslationOverride.objects.create(msgid="Hello", language="ru", text="Привет")
        
        with pytest.raises(Exception): # IntegrityError or similar depending on DB
            TranslationOverride.objects.create(msgid="Hello", language="ru", text="Здравствуй")

    def test_inactive_override_not_applied(self):
        """Inactive overrides should not be returned by runtime."""
        TranslationOverride.objects.create(msgid="Hello", language="ru", text="Привет", is_active=False)
        
        translated = apply_db_override("Hello", "Original", "ru")
        assert translated == "Original"

    def test_active_override_applied(self):
        """Active overrides should be returned by runtime."""
        TranslationOverride.objects.create(msgid="Hello", language="ru", text="Привет", is_active=True)
        
        translated = apply_db_override("Hello", "Original", "ru")
        assert translated == "Привет"

    def test_override_can_match_translated_result(self):
        """Runtime should recover when gettext returns a stale translated value."""
        TranslationOverride.objects.create(
            msgid="Nowy klient",
            language="ru",
            text="Новый клиент",
            is_active=True,
        )

        translated = apply_db_override("Новый клиент", "Nowy klient", "ru")

        assert translated == "Новый клиент"

    def test_cache_usage_and_clear(self):
        """Runtime should use cache and clear it on update."""
        TranslationOverride.objects.create(msgid="Hello", language="ru", text="Привет", is_active=True)
        
        # First call hits DB
        translated = apply_db_override("Hello", "Original", "ru")
        assert translated == "Привет"
        
        # Update DB directly without clearing cache
        TranslationOverride.objects.filter(msgid="Hello", language="ru").update(text="Здравствуй")
        
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
        with patch('translations.models.TranslationOverride.objects.filter') as mock_filter:
            mock_filter.side_effect = ProgrammingError("Table does not exist")
            
            # Should not raise exception
            translated = apply_db_override("Hello", "Original", "ru")
            assert translated == "Original"

    def test_utils_save_to_db(self):
        """save_translation_entry should save to DB when storage=database."""
        save_translation_entry("Hello", ru="Привет", storage="database")
        
        override = TranslationOverride.objects.filter(msgid="Hello", language="ru").first()
        assert override is not None
        assert override.text == "Привет"

    def test_utils_load_overlays_db(self):
        """load_all_translations should overlay DB on top of PO."""
        TranslationOverride.objects.create(msgid="Clients", language="ru", text="Клиенты из БД", is_active=True)
        
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
        
        # Import dry-run
        call_command('import_po_to_db', '--dry-run')
        assert TranslationOverride.objects.count() == 0
        
        # Export dry-run
        TranslationOverride.objects.create(msgid="Hello", language="ru", text="Привет", is_active=True)
        call_command('export_db_translations_to_po', '--dry-run')

    def test_import_po_updates_imported_overrides_by_default(self):
        """Imported DB rows should track the current PO file on release sync."""
        from django.core.management import call_command

        expected = "\u041d\u0430\u0432\u0438\u0433\u0430\u0446\u0438\u044f \u043f\u043e \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u0430\u043c"
        TranslationOverride.objects.create(
            msgid="Pagination",
            language="ru",
            text="Old import",
            source=TranslationOverride.SOURCE_IMPORT,
            is_active=True,
        )
        assert apply_db_override("Pagination", "fallback", "ru") == "Old import"

        call_command("import_po_to_db", verbosity=0)

        override = TranslationOverride.objects.get(msgid="Pagination", language="ru")
        assert override.text == expected
        assert override.source == TranslationOverride.SOURCE_IMPORT
        assert apply_db_override("Pagination", "fallback", "ru") == expected

    def test_import_po_preserves_studio_overrides_by_default(self):
        """Release sync must not overwrite manual Translation Studio edits."""
        from django.core.management import call_command

        TranslationOverride.objects.create(
            msgid="Pagination",
            language="ru",
            text="Manual studio edit",
            source=TranslationOverride.SOURCE_STUDIO,
            is_active=True,
        )

        call_command("import_po_to_db", verbosity=0)

        override = TranslationOverride.objects.get(msgid="Pagination", language="ru")
        assert override.text == "Manual studio edit"
        assert override.source == TranslationOverride.SOURCE_STUDIO

    def test_import_po_can_overwrite_selected_studio_sources(self):
        """Operators can repair bad production DB overrides from PO without enabling a broad overwrite."""
        from django.core.management import call_command

        expected = "\u041d\u0430\u0432\u0438\u0433\u0430\u0446\u0438\u044f \u043f\u043e \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u0430\u043c"
        TranslationOverride.objects.create(
            msgid="Pagination",
            language="ru",
            text="Bad studio edit",
            source=TranslationOverride.SOURCE_STUDIO,
            is_active=True,
        )

        call_command("import_po_to_db", "--overwrite-sources=studio", verbosity=0)

        override = TranslationOverride.objects.get(msgid="Pagination", language="ru")
        assert override.text == expected
        assert override.source == TranslationOverride.SOURCE_IMPORT

    def test_import_po_can_fail_on_protected_skips(self):
        """A dry production audit can fail when protected DB overrides differ from PO."""
        from django.core.management import call_command
        from django.core.management.base import CommandError

        TranslationOverride.objects.create(
            msgid="Pagination",
            language="ru",
            text="Protected studio edit",
            source=TranslationOverride.SOURCE_STUDIO,
            is_active=True,
        )

        with pytest.raises(CommandError):
            call_command("import_po_to_db", "--dry-run", "--fail-on-skipped", verbosity=0)
