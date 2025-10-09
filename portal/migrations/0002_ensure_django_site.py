from django.conf import settings
from django.db import migrations


def _determine_domain_and_name():
    import os

    candidates = [
        os.environ.get("SITE_DOMAIN"),
        getattr(settings, "SITE_DOMAIN", None),
        os.environ.get("RENDER_EXTERNAL_HOSTNAME"),
    ]

    allowed_hosts = getattr(settings, "ALLOWED_HOSTS", []) or []
    for host in allowed_hosts:
        if host and host not in {"127.0.0.1", "localhost"} and not host.startswith("[::1]"):
            candidates.append(host)

    for candidate in candidates:
        if candidate:
            return candidate, candidate

    return "example.com", "example.com"


def ensure_site_exists(apps, schema_editor):
    connection = schema_editor.connection
    introspection = connection.introspection

    table_names = set(introspection.table_names())
    Site = apps.get_model("sites", "Site")

    if "django_site" not in table_names:
        schema_editor.create_model(Site)

    domain, name = _determine_domain_and_name()
    site_id = getattr(settings, "SITE_ID", 1)

    Site.objects.using(connection.alias).update_or_create(
        id=site_id,
        defaults={"domain": domain, "name": name},
    )


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(ensure_site_exists, migrations.RunPython.noop),
    ]
