from pathlib import Path


def test_desktop_notification_button_has_only_dropdown_toggle() -> None:
    template = Path("clients/templates/clients/onboarding/base_onboarding.html").read_text(encoding="utf-8")
    marker = 'id="notificationDropdown"'
    start = template.index(marker)
    button_start = template.rfind("<button", 0, start)
    button_end = template.index(">", start)
    button_html = template[button_start:button_end]

    assert 'data-bs-toggle="dropdown"' in button_html
    assert 'data-bs-toggle="tooltip"' not in button_html
    assert 'aria-expanded="false"' in button_html
    assert 'notification-badge-nav' in template[button_end: template.index("</button>", button_end)]
