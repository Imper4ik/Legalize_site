from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.test import override_settings
from django.utils.translation import gettext as _

from clients.models import TestRun
from clients.testing.assertions import ScenarioRecorder
from clients.testing.cleanup import cleanup_test_data
from clients.testing.scenarios import SCENARIO_GROUPS

SAFE_TEST_EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
TEST_CENTER_LOCK_KEY = "test_center:run_or_cleanup"


def ensure_test_center_enabled(*, user: Any | None = None) -> None:
    """Allow explicitly enabled superusers to use the Test Center."""
    if not getattr(settings, "ENABLE_TEST_CENTER", False):
        raise PermissionDenied(_("Test Center is disabled."))
    if user is not None and not getattr(user, "is_superuser", False):
        raise PermissionDenied(_("Test Center requires a superuser."))


def available_modes() -> list[str]:
    return list(SCENARIO_GROUPS.keys())


@contextmanager
def testcenter_lock() -> Any:
    acquired = cache.add(TEST_CENTER_LOCK_KEY, "1", timeout=60 * 60)
    if not acquired:
        raise RuntimeError(_("Another Test Center run or cleanup is already in progress."))
    try:
        yield
    finally:
        cache.delete(TEST_CENTER_LOCK_KEY)


def run_e2e_scenarios(
    *,
    mode: str,
    started_by: Any | None = None,
    cleanup: bool = True,
) -> TestRun:
    ensure_test_center_enabled(user=started_by if started_by is not None else None)
    if mode not in SCENARIO_GROUPS:
        raise ValueError(_("Unknown Test Center mode: %(mode)s") % {"mode": mode})

    with testcenter_lock():
        test_run = TestRun.objects.create(
            mode=mode,
            started_by=started_by if getattr(started_by, "is_authenticated", False) else None,
            is_test_data=True,
        )
        recorder = ScenarioRecorder(test_run)
        scenario_functions: Sequence[Callable[[ScenarioRecorder], None]] = SCENARIO_GROUPS[mode]
        media_root: str | None = None
        remove_media_root = False

        try:
            configured_media_root = str(getattr(settings, "TEST_CENTER_MEDIA_ROOT", "") or "").strip()
            if configured_media_root:
                media_root_path = Path(configured_media_root)
                media_root_path.mkdir(parents=True, exist_ok=True)
            else:
                media_parent = Path(tempfile.gettempdir())
                media_root_path = media_parent / f"legalize-test-center-{uuid4().hex}"
                media_root_path.mkdir(parents=True, exist_ok=False)
                remove_media_root = True
            media_root = str(media_root_path)
            allowed_hosts = list(getattr(settings, "ALLOWED_HOSTS", []))
            if "testserver" not in allowed_hosts:
                allowed_hosts.append("testserver")
            with override_settings(
                EMAIL_BACKEND=SAFE_TEST_EMAIL_BACKEND,
                MEDIA_ROOT=media_root,
                ALLOWED_HOSTS=allowed_hosts,
            ):
                for scenario in scenario_functions:
                    try:
                        scenario(recorder)
                    except Exception as exc:
                        recorder.check(
                            f"{scenario.__name__}.uncaught_exception",
                            False,
                            expected="scenario completes without exception",
                            actual=type(exc).__name__,
                            error_message=str(exc),
                        )
        finally:
            test_run.finish()
            if cleanup:
                cleanup_report = cleanup_test_data(include_test_runs=False, extra_media_roots=[media_root] if media_root else None)
                test_run.report_json = {
                    **(test_run.report_json or {}),
                    "cleanup": cleanup_report.as_dict(),
                }
                test_run.save(update_fields=["report_json"])
            if media_root and remove_media_root:
                shutil.rmtree(media_root, ignore_errors=True)

        return test_run
