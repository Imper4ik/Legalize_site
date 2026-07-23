"""Browser smoke test for CI: login and walk the key staff pages.

Catches the failure classes unit tests miss: JS console errors, 4xx/5xx on
page assets, and templates rendered with missing context variables (the
``INVALID_TEMPLATE_VAR`` sentinel from ``settings/test.py``).

Self-contained: migrates a file-based SQLite database, seeds demo data,
starts the dev server, drives Chromium through the pages, and cleans up.

Usage (CI or local, from the repository root):
    pip install playwright && playwright install --with-deps chromium
    python scripts/ui_smoke.py

Set ``UI_SMOKE_CHROMIUM_PATH`` to reuse a preinstalled Chromium binary.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8123"
DEMO_LOGIN = "demo-staff@example.test"
DEMO_PASSWORD = "DemoPass123!"
SENTINEL = "INVALID_TEMPLATE_VAR"
SMOKE_ENV = {
    "DJANGO_SETTINGS_MODULE": "legalize_site.settings.test",
    "TEST_DATABASE_URL": f"sqlite:///{REPO_ROOT / 'tmp' / 'ui-smoke.sqlite3'}",
    # Test settings run with DEBUG=False; runserver needs explicit hosts and
    # the --insecure flag below to serve static files in that mode.
    "ALLOWED_HOSTS": "127.0.0.1,localhost",
}

ROUTES = [
    "/ru/staff/",
    "/ru/staff/metrics/",
    "/ru/staff/tasks/",
    "/ru/staff/workday/",
    "/ru/staff/fingerprints-schedule/",
    "/ru/staff/reminders/documents/",
    "/ru/staff/reminders/payments/",
    "/ru/staff/mass-email/",
    "/ru/staff/admin-dashboard/",
    "/ru/staff/admin-panel/",
    "/pl/staff/",
]


def prepare_database() -> None:
    import django
    from django.core.management import call_command

    django.setup()
    # WhiteNoise serves /static/ from STATIC_ROOT when DEBUG is False.
    call_command("collectstatic", "--noinput", verbosity=0)
    call_command("migrate", "--noinput", verbosity=0)
    call_command("setup_roles", verbosity=0)
    call_command("seed_demo_data", "--confirm", verbosity=0)

    # allauth requires a verified email address before it lets the demo
    # account log in; seed_demo_data intentionally does not verify it.
    from allauth.account.models import EmailAddress
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(email__iexact=DEMO_LOGIN).first()
    if user is None:
        raise RuntimeError(f"seed_demo_data did not create {DEMO_LOGIN}")
    EmailAddress.objects.update_or_create(
        user=user, email=DEMO_LOGIN, defaults={"verified": True, "primary": True}
    )


def wait_for_server(url: str, timeout_seconds: int = 60) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"Server did not become ready at {url}")


def run_browser_tour() -> list[str]:
    from playwright.sync_api import sync_playwright

    problems: list[str] = []
    with sync_playwright() as p:
        launch_kwargs: dict[str, Any] = {}
        executable = os.environ.get("UI_SMOKE_CHROMIUM_PATH")
        if executable:
            launch_kwargs["executable_path"] = executable
        browser = p.chromium.launch(**launch_kwargs)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on(
            "console",
            lambda message: problems.append(f"console.error: {page.url} :: {message.text}")
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: problems.append(f"pageerror: {page.url} :: {error}"))
        page.on(
            "response",
            lambda response: problems.append(f"http {response.status}: {response.url}")
            if response.status >= 400 and "favicon" not in response.url
            else None,
        )

        page.goto(f"{BASE}/ru/accounts/login/")
        page.fill('input[name="login"]', DEMO_LOGIN)
        page.fill('input[name="password"]', DEMO_PASSWORD)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        if "/accounts/login" in page.url:
            problems.append(f"login failed: still on {page.url}")

        for route in ROUTES:
            page.goto(f"{BASE}{route}", wait_until="networkidle")
            body = page.content()
            if SENTINEL in body:
                problems.append(f"template sentinel on {route}")
            if not page.locator("nav, header, main, .container, .container-fluid").count():
                problems.append(f"page skeleton missing on {route}")

        browser.close()
    return problems


def main() -> int:
    os.chdir(REPO_ROOT)
    sys.path.insert(0, str(REPO_ROOT))
    for key, value in SMOKE_ENV.items():
        os.environ[key] = value
    (REPO_ROOT / "tmp").mkdir(exist_ok=True)
    db_path = Path(SMOKE_ENV["TEST_DATABASE_URL"].removeprefix("sqlite:///"))
    if db_path.exists():
        db_path.unlink()

    prepare_database()

    server = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", "127.0.0.1:8123", "--noreload", "--insecure"],
        env=os.environ.copy(),
    )
    try:
        wait_for_server(f"{BASE}/healthz/")
        problems = run_browser_tour()
    finally:
        server.terminate()
        server.wait(timeout=15)

    if problems:
        print("UI SMOKE FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"UI smoke passed: login + {len(ROUTES)} pages, no console errors, no 4xx/5xx, no missing template vars.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
