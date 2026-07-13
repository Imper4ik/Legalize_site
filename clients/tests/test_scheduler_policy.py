from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase


class SchedulerPolicyTests(SimpleTestCase):
    def test_background_automation_loop_is_opt_in(self):
        active_lines = [
            line.strip()
            for line in Path("start.sh").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

        self.assertIn(': "${ENABLE_BACKGROUND_AUTOMATION_LOOP:=false}"', active_lines)
        self.assertNotIn(': "${ENABLE_BACKGROUND_AUTOMATION_LOOP:=true}"', active_lines)
