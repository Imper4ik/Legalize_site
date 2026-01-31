"""
Audit Log Models - Track all user actions and model changes.

Provides comprehensive audit trail for security and debugging.
"""
from __future__ import annotations

import json
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class AuditLog(models.Model):
    """
    Audit log for tracking all user actions and model changes.
    
    Stores:
    - Who did what (user)
    - What action was performed (CREATE, UPDATE, DELETE, LOGIN, etc.)
    - On which object (content_type + object_id)
    - What changed (changes JSON field)
    - When it happened (timestamp)
    - From where (IP address, user agent)
    """
    
    class Action(models.TextChoices):
        CREATE = 'create', _('Создание')
        UPDATE = 'update', _('Обновление')
        DELETE = 'delete', _('Удаление')
        LOGIN = 'login', _('Вход')
        LOGOUT = 'logout', _('Выход')
        LOGIN_FAILED = 'login_failed', _('Неудачный вход')
        VIEW = 'view', _('Просмотр')
        EXPORT = 'export', _('Экспорт')
        EMAIL_SENT = 'email_sent', _('Отправка email')
        OCR_PARSE = 'ocr_parse', _('OCR парсинг')
        FILE_UPLOAD = 'file_upload', _('Загрузка файла')
        FILE_DELETE = 'file_delete', _('Удаление файла')
        CUSTOM = 'custom', _('Пользовательское действие')
    
    # Who
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        verbose_name=_('Пользователь'),
        help_text=_('Пользователь, выполнивший действие')
    )
    username = models.CharField(
        max_length=150,
        blank=True,
        default='',  # Default to empty string
        verbose_name=_('Имя пользователя'),
        help_text=_('Сохраняем имя для случаев, если пользователь удален')
    )
    
    # What action
    action = models.CharField(
        max_length=20,
        choices=Action.choices,
        db_index=True,
        verbose_name=_('Действие')
    )
    
    # On which object
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_('Тип объекта')
    )
    object_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name=_('ID объекта')
    )
    content_object = GenericForeignKey('content_type', 'object_id')
    object_repr = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_('Представление объекта'),
        help_text=_('Строковое представление объекта на момент действия')
    )
    
    # What changed (JSON)
    changes = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_('Изменения'),
        help_text=_('Детали изменений в формате JSON')
    )
    
    # Additional context
    description = models.TextField(
        blank=True,
        verbose_name=_('Описание'),
        help_text=_('Дополнительное описание действия')
    )
    
    # When
    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        verbose_name=_('Время')
    )
    
    # From where
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_('IP адрес')
    )
    user_agent = models.TextField(
        blank=True,
        verbose_name=_('User Agent')
    )
    
    # Request details
    request_path = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_('Путь запроса')
    )
    request_method = models.CharField(
        max_length=10,
        blank=True,
        verbose_name=_('HTTP метод')
    )
    
    class Meta:
        verbose_name = _('Лог действия')
        verbose_name_plural = _('Логи действий')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp'], name='auditlog_time_idx'),
            models.Index(fields=['user', '-timestamp'], name='auditlog_user_time_idx'),
            models.Index(fields=['action', '-timestamp'], name='auditlog_action_time_idx'),
            models.Index(fields=['content_type', '-timestamp'], name='auditlog_ctype_time_idx'),
            models.Index(fields=['ip_address', '-timestamp'], name='auditlog_ip_time_idx'),
        ]
    
    def __str__(self):
        user_str = self.username or 'System'
        action_str = self.get_action_display()
        
        if self.content_type and self.object_repr:
            return f"{user_str} - {action_str}: {self.content_type.model} '{self.object_repr}'"
        
        return f"{user_str} - {action_str}"
    
    @classmethod
    def log_action(
        cls,
        action: str,
        user=None,
        obj=None,
        changes: dict | None = None,
        description: str = '',
        request=None,
    ):
        """
        Create an audit log entry.
        
        Args:
            action: Action type (use Action enum)
            user: User who performed the action
            obj: Object that was acted upon
            changes: Dictionary of changes (old_value -> new_value)
            description: Additional description
            request: HTTP request object for IP/user-agent
        
        Returns:
            AuditLog instance
        
        Example:
            AuditLog.log_action(
                action=AuditLog.Action.CREATE,
                user=request.user,
                obj=client,
                changes={'status': {'old': 'new', 'new': 'active'}},
                description='Client created via web interface',
                request=request
            )
        """
        log_entry = cls(
            action=action,
            user=user,
            username=user.username if user else '',  # Empty string instead of None
            description=description,
        )
        
        # Set object reference
        if obj:
            log_entry.content_type = ContentType.objects.get_for_model(obj)
            log_entry.object_id = str(obj.pk)
            log_entry.object_repr = str(obj)[:500]
        
        # Set changes
        if changes:
            log_entry.changes = changes
        
        # Extract request info
        if request:
            log_entry.request_path = request.path[:500]
            log_entry.request_method = request.method
            
            # Get IP address
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                log_entry.ip_address = x_forwarded_for.split(',')[0].strip()
            else:
                log_entry.ip_address = request.META.get('REMOTE_ADDR')
            
            # Get user agent
            log_entry.user_agent = request.META.get('HTTP_USER_AGENT', '')[:1000]
        
        log_entry.save()
        return log_entry
    
    def get_changes_display(self):
        """Return formatted changes for display."""
        if not self.changes:
            return ''
        
        try:
            return json.dumps(self.changes, indent=2, ensure_ascii=False)
        except Exception:
            return str(self.changes)
