"""Mobile-layout regression: no page must scroll horizontally at 390px.

A non-wrapping flex row anywhere in the page pushes controls past the screen
edge and — because the bottom nav bar is position:fixed — drags the whole
viewport wide (the bug fixed in commit 1be09db). This test drives real pages
in headless chromium at an iPhone-sized viewport and fails on any horizontal
page overflow.

The test auto-skips when playwright or a chromium binary is unavailable
(plain CI); run `playwright install chromium` locally to enable it.
"""
from __future__ import annotations

import glob
import os

import pytest

playwright_sync = pytest.importorskip(
    "playwright.sync_api", reason="playwright is not installed"
)

from django.contrib.staticfiles.testing import StaticLiveServerTestCase  # noqa: E402

from clients.testing.factories import create_test_client, create_test_user  # noqa: E402

VIEWPORT = {"width": 390, "height": 844}


def _find_chromium() -> str | None:
    """Locate a chromium binary even when its build id mismatches the package."""
    roots = [
        os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""),
        os.path.expanduser("~/.cache/ms-playwright"),
    ]
    for root in roots:
        if not root:
            continue
        for pattern in ("chromium-*/chrome-linux/chrome", "chromium*/chrome-linux/chrome"):
            matches = sorted(glob.glob(os.path.join(root, pattern)))
            if matches:
                return matches[-1]
    return None


def _launch(pw):  # type: ignore[no-untyped-def]
    try:
        return pw.chromium.launch()
    except Exception:
        executable = _find_chromium()
        if not executable:
            pytest.skip("no chromium binary available for playwright")
        return pw.chromium.launch(executable_path=executable)


class MobileOverflowTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Sync playwright drives its own event loop inside the test thread.
        os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

    def _assert_no_horizontal_scroll(self, page, url_path: str) -> None:
        page.goto(f"{self.live_server_url}{url_path}", wait_until="networkidle")
        page.wait_for_timeout(300)
        metrics = page.evaluate(
            "() => ({vw: document.documentElement.clientWidth,"
            " sw: document.documentElement.scrollWidth})"
        )
        self.assertLessEqual(
            metrics["sw"],
            metrics["vw"] + 1,
            f"{url_path} scrolls horizontally on mobile: "
            f"scrollWidth={metrics['sw']} viewport={metrics['vw']}",
        )

    def test_staff_pages_do_not_scroll_horizontally_at_mobile_width(self):
        staff = create_test_user(role="Staff")
        client_obj = create_test_client(purpose="work")

        self.client.force_login(staff)
        session_cookie = self.client.cookies["sessionid"]

        with playwright_sync.sync_playwright() as pw:
            browser = _launch(pw)
            context = browser.new_context(viewport=VIEWPORT, is_mobile=True)
            context.add_cookies(
                [
                    {
                        "name": "sessionid",
                        "value": session_cookie.value,
                        "url": self.live_server_url,
                    }
                ]
            )
            page = context.new_page()
            try:
                for url_path in (
                    f"/ru/staff/client/{client_obj.pk}/",
                    "/ru/staff/tasks/",
                    "/ru/staff/clients/",
                ):
                    self._assert_no_horizontal_scroll(page, url_path)
            finally:
                context.close()
                browser.close()
