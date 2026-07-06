"""Gunicorn access logger that scrubs onboarding bearer tokens from logs.

Onboarding links carry a raw bearer token in the URL path
(``/<lang>/staff/onboarding/<token>/...``). Gunicorn's default access log
records the full request line, which would otherwise persist that token in
plaintext stdout/access logs (and any downstream log shipper) for the link's
whole lifetime — a replayable credential leak (audit Q-1).

Wire this logger in via ``--logger-class legalize_site.gunicorn_logging.RedactingLogger``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gunicorn.glogging import Logger as _GunicornLogger
else:
    try:  # pragma: no cover - gunicorn is only importable in the server environment
        from gunicorn.glogging import Logger as _GunicornLogger
    except Exception:  # pragma: no cover
        _GunicornLogger = object

# Match the path segment immediately after ``/onboarding/`` (the token) up to the
# next ``/``, whitespace or query separator, and replace it with a placeholder.
# Safe sentinels like ``me``/``current`` are redacted too — harmless.
_ONBOARDING_TOKEN_RE = re.compile(r"(/onboarding/)[^/\s?]+")
_REDACTED = r"\1[redacted]"

# Access-log atoms that can contain the request path: request line, URL path and
# the Referer header.
_PATH_ATOMS = ("r", "U", "f")


def redact_onboarding_path(value: Any) -> Any:
    """Replace the onboarding token segment in a log value, if present."""
    if not isinstance(value, str) or "/onboarding/" not in value:
        return value
    return _ONBOARDING_TOKEN_RE.sub(_REDACTED, value)


def redact_atoms(data: dict[str, Any]) -> dict[str, Any]:
    """Redact onboarding tokens from the path-bearing access-log atoms in place."""
    for key in _PATH_ATOMS:
        if key in data:
            data[key] = redact_onboarding_path(data[key])
    return data


class RedactingLogger(_GunicornLogger):
    """Gunicorn ``Logger`` that strips onboarding tokens from access-log atoms."""

    def atoms(self, resp: Any, req: Any, environ: Any, request_time: Any) -> dict[str, Any]:
        return redact_atoms(super().atoms(resp, req, environ, request_time))
