from django.template import Context, Template, engines
from django.test import SimpleTestCase, override_settings


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

    @override_settings(
        TEMPLATES=[
            {
                'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'DIRS': [],
                'APP_DIRS': True,
                'OPTIONS': {},
            }
        ]
    )
    def test_blocktranslate_alias_survives_engine_rebuild(self):
        engines._engines.clear()
        self.addCleanup(engines._engines.clear)

        template = Template("""
            {% blocktranslate %}Совместимость после пересоздания движка{% endblocktranslate %}
        """)
        rendered = template.render(Context({}))
        self.assertIn("Совместимость после пересоздания движка", rendered)
