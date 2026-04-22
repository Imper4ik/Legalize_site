from __future__ import annotations

import uuid

try:
    import sentry_sdk
except Exception:  # pragma: no cover - optional dependency
    sentry_sdk = None

from legalize_site.utils.logging import clear_log_context, set_log_context


class RequestIDMiddleware:
    REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"
    RESPONSE_HEADER = "X-Request-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get(self.REQUEST_ID_HEADER) or uuid.uuid4().hex
        correlation_id = request.META.get(self.REQUEST_ID_HEADER) or request_id
        request.request_id = request_id
        request.correlation_id = correlation_id
        set_log_context(request_id=request_id, correlation_id=correlation_id)

        if sentry_sdk is not None:
            scope = sentry_sdk.get_current_scope()
            scope.set_tag("request_id", request_id)
            scope.set_tag("correlation_id", correlation_id)

        try:
            response = self.get_response(request)
        finally:
            clear_log_context()

        response[self.RESPONSE_HEADER] = request_id
        return response
