from __future__ import annotations

import logging
import os
import secrets
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

CronView = Callable[..., HttpResponse]


def primary_cron_token_required(view_func: CronView) -> CronView:
    """Require CRON_TOKEN before delegating to a non-backup cron endpoint.

    The legacy BACKUP_TRIGGER_SECRET remains accepted by the database-backup
    endpoint only. This outer guard prevents that legacy token from inheriting
    permissions to OCR, email, reminders, or retention jobs through the shared
    authorization helper in ``cron_views``.
    """

    @csrf_exempt
    @wraps(view_func)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        expected_token = os.environ.get("CRON_TOKEN", "").strip()
        supplied_token = request.headers.get("X-CRON-TOKEN", "").strip()
        authorization = request.headers.get("Authorization", "")
        if not supplied_token and authorization.startswith("Bearer "):
            supplied_token = authorization.removeprefix("Bearer ").strip()

        valid_token = (
            bool(expected_token)
            and bool(supplied_token)
            and secrets.compare_digest(supplied_token, expected_token)
        )
        if not valid_token:
            logger.warning("Rejected non-backup cron request without a valid CRON_TOKEN")
            return JsonResponse({"error": "forbidden"}, status=403)

        return view_func(request, *args, **kwargs)

    return wrapped
