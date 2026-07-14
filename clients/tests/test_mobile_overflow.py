"""Mobile-layout regression: no page must scroll horizontally at 390px.

A non-wrapping flex row anywhere in the page pushes controls past the screen
edge and — because the bottom nav bar is position:fixed — drags the whole
viewport wide (the bug fixed in commit 1be09db). This test drives real pages
in headless chromium at an iPhone-sized viewport and fails on any horizontal
page overflow.

Skips cleanly under both pytest and the Django/unittest runner when playwright
or a chromium binary is unavailable (plain CI); run `playwright install
chromium` locally to enable it.
"""
from __future__ import annotations

import glob
import os
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - exercised only without playwright
    sync_playwright = None  # type: ignore[assignment]

from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from clients.testing.factories import create_test_client, create_test_user

VIEWPORT = {"width": 390, "height": 844}


def _find_chromium() -> str | None:
    """Locate a chromium binary even when its build id mismatches the package."""
    roots = [
        os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""),
        os.path.expanduser("~/.cache/ms-playwright"),
        os.path.expanduser("~/Library/Caches/ms-playwright"),
    ]
    patterns = (
        "chromium-*/chrome-linux/chrome",
        "chromium*/chrome-linux/chrome",
        "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
    )
    for root in roots:
        if not root:
            continue
        for pattern in patterns:
            matches = sorted(glob.glob(os.path.join(root, pattern)))
            if matches:
                return matches[-1]
    return None


CHROMIUM_PATH = _find_chromium() if sync_playwright is not None else None


@unittest.skipUnless(
    sync_playwright is not None and CHROMIUM_PATH,
    "playwright and a chromium binary are required (run `playwright install chromium`)",
)
class MobileOverflowTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Sync playwright drives its own event loop inside the test thread.
        os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

    def _launch(self, pw):  # type: ignore[no-untyped-def]
        try:
            return pw.chromium.launch()
        except Exception:
            # Package build id mismatch: fall back to the located binary.
            return pw.chromium.launch(executable_path=CHROMIUM_PATH)

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

        with sync_playwright() as pw:
            browser = self._launch(pw)
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
