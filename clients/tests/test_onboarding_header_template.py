from pathlib import Path

from django.test import SimpleTestCase


class OnboardingHeaderTemplateTests(SimpleTestCase):
    def _template(self) -> str:
        return Path("clients/templates/clients/onboarding/base_onboarding.html").read_text()

    def test_desktop_notification_button_has_only_dropdown_toggle(self) -> None:
        template = self._template()
        marker = 'id="notificationDropdown"'
        start = template.index(marker)
        button_start = template.rfind("<button", 0, start)
        button_end = template.index(">", start)
        button_html = template[button_start:button_end]

        self.assertIn('data-bs-toggle="dropdown"', button_html)
        self.assertNotIn('data-bs-toggle="tooltip"', button_html)
        self.assertIn('aria-expanded="false"', button_html)
        self.assertIn('notification-badge-nav', template[button_end: template.index("</button>", button_end)])

    def test_desktop_header_uses_compact_language_dropdown_with_all_languages(self) -> None:
        template = self._template()
        marker = 'id="languageDropdown"'
        start = template.index(marker)
        menu_start = template.index('<ul class="dropdown-menu', start)
        menu_end = template.index('</ul>', menu_start)
        menu_html = template[menu_start:menu_end]

        self.assertIn('{{ LANGUAGE_CODE|upper }}', template[start:menu_start])
        self.assertIn('name="language" value="{{ lang.0 }}"', menu_html)
        self.assertIn('aria-current="true"', menu_html)
        self.assertNotIn('lang.0 != LANGUAGE_CODE', menu_html)

    def test_onboarding_header_keeps_cta_primary_and_theme_icon_only(self) -> None:
        template = self._template()

        self.assertIn('class="btn btn-cta-question"', template)
        self.assertIn('class="btn btn-secondary-cabinet dropdown-toggle"', template)
        self.assertIn('data-theme-toggle', template)
        self.assertNotIn('Тёмная тема', template)
