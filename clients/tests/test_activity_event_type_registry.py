"""Every event_type written anywhere in the code must be a declared choice.

Undeclared event types render as raw English slugs in the RODO activity
journal (no translation via ``get_event_type_display``) and are invisible to
any filtering built on ``EVENT_TYPE_CHOICES``.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

from clients.models import ClientActivity
from clients.models.permissions import StaffAuditEvent

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCANNED_DIRS = ("clients", "submissions", "users", "translations", "database_media")
EXCLUDED_PARTS = {"tests", "migrations", "__pycache__", "testing"}
EVENT_TYPE_LITERAL = re.compile(r"""event_type=["']([a-z0-9_]+)["']""")


def _emitted_event_types() -> set[str]:
    found: set[str] = set()
    for scanned_dir in SCANNED_DIRS:
        for path in (PROJECT_ROOT / scanned_dir).rglob("*.py"):
            if EXCLUDED_PARTS.intersection(path.parts):
                continue
            found.update(EVENT_TYPE_LITERAL.findall(path.read_text(encoding="utf-8")))
    return found


class ActivityEventTypeRegistryTests(SimpleTestCase):
    def test_every_emitted_event_type_is_declared(self) -> None:
        declared = {value for value, _label in ClientActivity.EVENT_TYPE_CHOICES}
        declared |= {value for value, _label in StaffAuditEvent.EVENT_TYPE_CHOICES}

        undeclared = _emitted_event_types() - declared

        self.assertFalse(
            undeclared,
            "event_type values written in code but missing from EVENT_TYPE_CHOICES "
            f"(raw untranslated slugs in the activity journal): {sorted(undeclared)}",
        )

    def test_every_client_activity_choice_has_a_badge_class(self) -> None:
        activity = ClientActivity()
        for value, _label in ClientActivity.EVENT_TYPE_CHOICES:
            activity.event_type = value
            self.assertTrue(activity.badge_class)
