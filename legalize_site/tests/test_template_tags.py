from django.template import Context, Template
from django.test import SimpleTestCase


class I18NCompatibilityTagsTests(SimpleTestCase):
    def test_blocktranslate_alias_renders(self):
        template = Template("""
            {% load i18n %}
            {% blocktranslate with name='Мир' %}Привет, {{ name }}{% endblocktranslate %}
        """)
        rendered = template.render(Context({}))
        self.assertIn("Привет, Мир", rendered)

    def test_blocktranslate_without_load_still_available(self):
        template = Template("""
            {% blocktranslate %}Строка без явной загрузки i18n{% endblocktranslate %}
        """)
        rendered = template.render(Context({}))
        self.assertIn("Строка без явной загрузки i18n", rendered)
