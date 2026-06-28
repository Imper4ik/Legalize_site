"""Action buttons inside the "Риски" alert cards must use the theme-aware
btn-alert-action class (readable on the dark alert background), not the
invisible btn-outline-dark.
"""
from __future__ import annotations

from django.template.loader import render_to_string
from django.test import SimpleTestCase


class WorkflowPanelButtonContrastTests(SimpleTestCase):
    def _render(self) -> str:
        context = {
            "workflow_summary": {"alerts_count": 2, "automatic_checks": []},
            "workflow_alerts": [
                {
                    "level": "warning",
                    "title": "Есть wezwanie без номера дела",
                    "message": "Проверьте распознавание или заполните case number вручную.",
                    "action_label": "Открыть карточку",
                    "action_url": "/x/",
                },
                {
                    "level": "warning",
                    "title": "Есть OCR-данные без подтверждения",
                    "message": "Подтвердите распознанные данные.",
                    "actions": [
                        {"is_ocr_review": True, "label": "Проверить документ", "doc_id": 1, "doc_type": "passport"},
                    ],
                },
            ],
        }
        return render_to_string("clients/partials/workflow_panel.html", context)

    def test_alert_action_buttons_use_readable_class(self) -> None:
        html = self._render()
        self.assertNotIn("btn-outline-dark", html)
        # Both the link action and the OCR-confirm button are visible.
        self.assertEqual(html.count("btn-alert-action"), 2)
        self.assertIn("review-ocr-data-btn", html)
