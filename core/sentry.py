"""
Sentry integration for error monitoring.

Setup:
1. Create account at https://sentry.io (FREE tier available!)
2. Create new project for Django
3. Copy DSN
4. Add SENTRY_DSN to Railway environment variables

Free tier includes:
- 5,000 events/month
- 1 user
- 30 days retention
- Email alerts
"""

import os
import logging

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

logger = logging.getLogger(__name__)


def init_sentry():
    """
    Initialize Sentry for error tracking.
    
    Only runs in production (when DEBUG=False and SENTRY_DSN is set).
    """
    sentry_dsn = os.getenv("SENTRY_DSN")
    environment = os.getenv("SENTRY_ENVIRONMENT", "production")
    
    if not sentry_dsn:
        logger.info("Sentry DSN not configured, skipping Sentry initialization")
        return
    
    # Sentry logging integration
    sentry_logging = LoggingIntegration(
        level=logging.INFO,        # Capture info and above as breadcrumbs
        event_level=logging.ERROR  # Send errors as events
    )
    
    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[
            DjangoIntegration(),
            sentry_logging,
        ],
        
        # Set traces_sample_rate to 1.0 to capture 100% of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        
        # If you wish to associate users to errors (assuming you are using
        # django.contrib.auth) you may enable sending PII data.
        send_default_pii=True,
        
        # Environment (production, staging, development)
        environment=environment,
        
        # Release version (optional - good for tracking which version has bugs)
        release=os.getenv("RAILWAY_GIT_COMMIT_SHA", None),
        
        # Before send hook - can filter/modify events
        before_send=before_send_hook,
    )
    
    logger.info(f"Sentry initialized for environment: {environment}")


def before_send_hook(event, hint):
    """
    Hook called before sending event to Sentry.
    
    Can be used to:
    - Filter out certain errors
    - Modify event data
    - Scrub sensitive information
    """
    
    # Don't send certain exceptions
    if 'exc_info' in hint:
        exc_type, exc_value, tb = hint['exc_info']
        
        # Ignore 404 errors
        if exc_type.__name__ == 'Http404':
            return None
        
        # Ignore DisallowedHost errors (bots scanning)
        if exc_type.__name__ == 'DisallowedHost':
            return None
    
    # Scrub sensitive data from breadcrumbs
    if 'breadcrumbs' in event:
        for crumb in event['breadcrumbs']:
            if 'message' in crumb:
                # Remove passwords from messages
                crumb['message'] = crumb['message'].replace('password', '***')
    
    return event


# Helper functions for manual error tracking

def capture_exception(error, **context):
    """
    Manually capture an exception with context.
    
    Example:
        try:
            process_payment(client)
        except Exception as e:
            capture_exception(e, client_id=client.id, amount=1000)
            raise
    """
    with sentry_sdk.push_scope() as scope:
        for key, value in context.items():
            scope.set_context(key, {"value": str(value)})
        sentry_sdk.capture_exception(error)


def capture_message(message, level='info', **context):
    """
    Manually capture a message (not an exception).
    
    Example:
        capture_message(
            "Client created without email",
            level='warning',
            client_id=client.id
        )
    """
    with sentry_sdk.push_scope() as scope:
        for key, value in context.items():
            scope.set_context(key, {"value": str(value)})
        sentry_sdk.capture_message(message, level=level)


# Example usage in views:
"""
from core.sentry import capture_exception, capture_message

def client_create_view(request):
    try:
        client = Client.objects.create(...)
        
        if not client.email:
            capture_message(
                "Client created without email",
                level='warning',
                client_id=client.id
            )
        
        return redirect('client_detail', pk=client.id)
        
    except Exception as e:
        capture_exception(e, 
            form_data=request.POST,
            user=request.user.username
        )
        raise
"""
