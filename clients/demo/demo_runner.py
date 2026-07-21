from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.test import override_settings
from django.utils.translation import gettext as _

from clients.demo.demo_scenarios import prepare_demo_scenarios

SAFE_DEMO_EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
DEMO_CENTER_LOCK_KEY = "demo_center:run_or_cleanup"


def ensure_demo_center_enabled(*, user: Any | None = None) -> None:
    """Allow explicitly enabled superusers to use the Demo Center."""
    if not getattr(settings, "DEMO_MODE_ENABLED", False):
        raise PermissionDenied(_("Demo Center is disabled."))
    if user is not None and not getattr(user, "is_superuser", False):
        raise PermissionDenied(_("Demo Center requires a superuser."))


@contextmanager
def democenter_lock() -> Any:
    acquired = cache.add(DEMO_CENTER_LOCK_KEY, "1", timeout=60 * 60)
    if not acquired:
        raise RuntimeError(_("Another Demo Center run or cleanup is already in progress."))
    try:
        yield
    finally:
        cache.delete(DEMO_CENTER_LOCK_KEY)


def prepare_demo(started_by: Any) -> list[dict[str, Any]]:
    ensure_demo_center_enabled(user=started_by)

    with democenter_lock():
        media_root: str | None = None

        configured_media_root = str(getattr(settings, "DEMO_CENTER_MEDIA_ROOT", "") or "").strip()
        if configured_media_root:
            media_root_path = Path(configured_media_root)
            media_root_path.mkdir(parents=True, exist_ok=True)
            media_root = str(media_root_path)
        else:
            # Fallback to a subfolder under base MEDIA_ROOT or temp dir
            base_media = Path(settings.MEDIA_ROOT or tempfile.gettempdir())
            media_root_path = base_media / "demo_center_media"
            media_root_path.mkdir(parents=True, exist_ok=True)
            media_root = str(media_root_path)

        allowed_hosts = list(getattr(settings, "ALLOWED_HOSTS", []))
        if "testserver" not in allowed_hosts:
            allowed_hosts.append("testserver")

        with override_settings(
            EMAIL_BACKEND=SAFE_DEMO_EMAIL_BACKEND,
            MEDIA_ROOT=media_root,
            ALLOWED_HOSTS=allowed_hosts,
        ):
            results = prepare_demo_scenarios(started_by)
            return results
