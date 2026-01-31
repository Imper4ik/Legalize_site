"""
Audit Middleware - Capture HTTP requests and make request available to signals.

Stores request in thread-local storage so signals can access it.
"""
from __future__ import annotations

import logging
import time
from django.utils.deprecation import MiddlewareMixin

from .audit_signals import set_current_request, clear_current_request
from .models import AuditLog

logger = logging.getLogger(__name__)


class AuditMiddleware(MiddlewareMixin):
    """
    Middleware to make request available to audit signals.
    
    Also logs slow requests and errors.
    """
    
    def process_request(self, request):
        """Store request in thread-local and record start time."""
        set_current_request(request)
        request._audit_start_time = time.time()
        return None
    
    def process_response(self, request, response):
        """Log slow requests and clear request from thread-local."""
        # Calculate request duration
        if hasattr(request, '_audit_start_time'):
            duration = time.time() - request._audit_start_time
            
            # Log slow requests (>2 seconds)
            if duration > 2.0:
                logger.warning(
                    f"Slow request: {request.method} {request.path} "
                    f"took {duration:.2f}s (status: {response.status_code})"
                )
                
                # Optionally log to audit trail
                if request.user.is_authenticated:
                    AuditLog.log_action(
                        action=AuditLog.Action.CUSTOM,
                        user=request.user,
                        description=f"Slow request: {request.method} {request.path} ({duration:.2f}s)",
                        request=request,
                        changes={'duration_seconds': duration, 'status_code': response.status_code}
                    )
        
        # Clear request from thread-local
        clear_current_request()
        return response
    
    def process_exception(self, request, exception):
        """Log exceptions."""
        logger.error(
            f"Exception in request: {request.method} {request.path}",
            exc_info=exception
        )
        
        # Log to audit trail
        if request.user.is_authenticated:
            AuditLog.log_action(
                action=AuditLog.Action.CUSTOM,
                user=request.user,
                description=f"Exception: {type(exception).__name__}: {str(exception)}",
                request=request,
                changes={'exception_type': type(exception).__name__}
            )
        
        clear_current_request()
        return None
