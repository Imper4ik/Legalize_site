"""
Audit Signal Handlers - Automatically log model changes.

Tracks CREATE, UPDATE, DELETE operations on important models.
"""
from __future__ import annotations

import logging
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed

from clients.models import Client, Document, Payment, Reminder
from submissions.models import Submission
from .models import AuditLog

logger = logging.getLogger(__name__)

# Thread-local storage for request context
_thread_locals = None

try:
    import threading
    _thread_locals = threading.local()
except ImportError:
    logger.warning('Threading not available, audit request context will not work')


def get_current_request():
    """Get current request from thread-local storage."""
    return getattr(_thread_locals, 'request', None)


def set_current_request(request):
    """Set current request in thread-local storage."""
    if _thread_locals is not None:
        _thread_locals.request = request


def clear_current_request():
    """Clear current request from thread-local storage."""
    if _thread_locals is not None:
        _thread_locals.request = None


# --- CLIENT MODEL LOGGING ---

@receiver(post_save, sender=Client)
def log_client_save(sender, instance, created, **kwargs):
    """Log client creation and updates."""
    action = AuditLog.Action.CREATE if created else AuditLog.Action.UPDATE
    request = get_current_request()
    
    changes = {}
    if not created and hasattr(instance, '_old_values'):
        # Track what changed
        for field in ['first_name', 'last_name', 'email', 'phone', 'status', 
                     'application_purpose', 'case_number']:
            old_val = instance._old_values.get(field)
            new_val = getattr(instance, field, None)
            if old_val != new_val:
                changes[field] = {'old': str(old_val), 'new': str(new_val)}
    
    AuditLog.log_action(
        action=action,
        user=request.user if request and request.user.is_authenticated else None,
        obj=instance,
        changes=changes if changes else None,
        description=f"Client {'created' if created else 'updated'}",
        request=request
    )


@receiver(pre_save, sender=Client)
def store_old_client_values(sender, instance, **kwargs):
    """Store old values before save for comparison."""
    if instance.pk:
        try:
            old_instance = Client.objects.get(pk=instance.pk)
            instance._old_values = {
                'first_name': old_instance.first_name,
                'last_name': old_instance.last_name,
                'email': old_instance.email,
                'phone': old_instance.phone,
                'status': old_instance.status,
                'application_purpose': old_instance.application_purpose,
                'case_number': old_instance.case_number,
            }
        except Client.DoesNotExist:
            instance._old_values = {}


@receiver(post_delete, sender=Client)
def log_client_delete(sender, instance, **kwargs):
    """Log client deletion."""
    request = get_current_request()
    
    AuditLog.log_action(
        action=AuditLog.Action.DELETE,
        user=request.user if request and request.user.is_authenticated else None,
        obj=None,  # Object is deleted, just store representation
        changes={'deleted_object': str(instance)},
        description=f"Client deleted: {instance}",
        request=request
    )


# --- DOCUMENT MODEL LOGGING ---

@receiver(post_save, sender=Document)
def log_document_save(sender, instance, created, **kwargs):
    """Log document uploads and updates."""
    action = AuditLog.Action.FILE_UPLOAD if created else AuditLog.Action.UPDATE
    request = get_current_request()
    
    changes = {}
    if created:
        changes = {
            'document_type': instance.document_type,
            'client': str(instance.client),
            'file': instance.file.name if instance.file else None,
        }
    
    AuditLog.log_action(
        action=action,
        user=request.user if request and request.user.is_authenticated else None,
        obj=instance,
        changes=changes if changes else None,
        description=f"Document {'uploaded' if created else 'updated'}",
        request=request
    )


@receiver(post_delete, sender=Document)
def log_document_delete(sender, instance, **kwargs):
    """Log document deletion."""
    request = get_current_request()
    
    AuditLog.log_action(
        action=AuditLog.Action.FILE_DELETE,
        user=request.user if request and request.user.is_authenticated else None,
        obj=None,
        changes={
            'deleted_document': str(instance),
            'document_type': instance.document_type,
            'client': str(instance.client),
        },
        description=f"Document deleted: {instance}",
        request=request
    )


# --- PAYMENT MODEL LOGGING ---

@receiver(post_save, sender=Payment)
def log_payment_save(sender, instance, created, **kwargs):
    """Log payment creation and updates."""
    action = AuditLog.Action.CREATE if created else AuditLog.Action.UPDATE
    request = get_current_request()
    
    changes = {}
    if created:
        changes = {
            'client': str(instance.client),
            'total_amount': str(instance.total_amount),
            'service_description': instance.service_description,
            'status': instance.status,
        }
    elif hasattr(instance, '_old_values'):
        for field in ['total_amount', 'amount_paid', 'status', 'service_description']:
            old_val = instance._old_values.get(field)
            new_val = getattr(instance, field, None)
            if old_val != new_val:
                changes[field] = {'old': str(old_val), 'new': str(new_val)}
    
    AuditLog.log_action(
        action=action,
        user=request.user if request and request.user.is_authenticated else None,
        obj=instance,
        changes=changes if changes else None,
        description=f"Payment {'created' if created else 'updated'}",
        request=request
    )


@receiver(pre_save, sender=Payment)
def store_old_payment_values(sender, instance, **kwargs):
    """Store old payment values before save."""
    if instance.pk:
        try:
            old_instance = Payment.objects.get(pk=instance.pk)
            instance._old_values = {
                'total_amount': old_instance.total_amount,
                'amount_paid': old_instance.amount_paid,
                'status': old_instance.status,
                'service_description': old_instance.service_description,
            }
        except Payment.DoesNotExist:
            instance._old_values = {}


@receiver(post_delete, sender=Payment)
def log_payment_delete(sender, instance, **kwargs):
    """Log payment deletion."""
    request = get_current_request()
    
    AuditLog.log_action(
        action=AuditLog.Action.DELETE,
        user=request.user if request and request.user.is_authenticated else None,
        obj=None,
        changes={
            'deleted_payment': str(instance),
            'client': str(instance.client),
            'amount': str(instance.total_amount),
        },
        description=f"Payment deleted: {instance}",
        request=request
    )


# --- AUTHENTICATION LOGGING ---

@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Log successful user login."""
    AuditLog.log_action(
        action=AuditLog.Action.LOGIN,
        user=user,
        description=f"User logged in successfully",
        request=request
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Log user logout."""
    AuditLog.log_action(
        action=AuditLog.Action.LOGOUT,
        user=user,
        description=f"User logged out",
        request=request
    )


@receiver(user_login_failed)
def log_login_failed(sender, credentials, request, **kwargs):
    """Log failed login attempts."""
    username = credentials.get('username', 'Unknown'
)
    
    AuditLog.log_action(
        action=AuditLog.Action.LOGIN_FAILED,
        user=None,
        description=f"Failed login attempt for username: {username}",
        request=request,
        changes={'username_attempted': username}
    )


# --- SUBMISSION LOGGING ---

@receiver(post_save, sender=Submission)
def log_submission_save(sender, instance, created, **kwargs):
    """Log submission creation and updates."""
    action = AuditLog.Action.CREATE if created else AuditLog.Action.UPDATE
    request = get_current_request()
    
    changes = {}
    if created:
        changes = {
            'name': instance.name,
            'slug': instance.slug,
            'status': instance.status,
        }
    
    AuditLog.log_action(
        action=action,
        user=request.user if request and request.user.is_authenticated else None,
        obj=instance,
        changes=changes if changes else None,
        description=f"Submission {'created' if created else 'updated'}",
        request=request
    )


@receiver(post_delete, sender=Submission)
def log_submission_delete(sender, instance, **kwargs):
    """Log submission deletion."""
    request = get_current_request()
    
    AuditLog.log_action(
        action=AuditLog.Action.DELETE,
        user=request.user if request and request.user.is_authenticated else None,
        obj=None,
        changes={'deleted_submission': str(instance)},
        description=f"Submission deleted: {instance}",
        request=request
    )
