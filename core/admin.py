"""Admin interface for core models."""
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.contrib.contenttypes.models import ContentType
import json

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin interface for viewing audit logs."""
    
    list_display = [
        'timestamp',
        'colored_action',
        'user_link',
        'object_link',
        'ip_address',
        'short_description',
    ]
    
    list_filter = [
        'action',
        'timestamp',
        ('user', admin.RelatedOnlyFieldListFilter),
        'content_type',
    ]
    
    search_fields = [
        'username',
        'object_repr',
        'description',
        'ip_address',
    ]
    
    readonly_fields = [
        'user',
        'username',
        'action',
        'content_type',
        'object_id',
        'object_repr',
        'formatted_changes',
        'description',
        'timestamp',
        'ip_address',
        'user_agent',
        'request_path',
        'request_method',
    ]
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('timestamp', 'user', 'username', 'action')
        }),
        ('Объект', {
            'fields': ('content_type', 'object_id', 'object_repr')
        }),
        ('Изменения', {
            'fields': ('formatted_changes', 'description'),
            'classes': ('collapse',)
        }),
        ('Контекст запроса', {
            'fields': ('ip_address', 'user_agent', 'request_path', 'request_method'),
            'classes': ('collapse',)
        }),
    )
    
    date_hierarchy = 'timestamp'
    
    # Pagination
    list_per_page = 100
    
    def has_add_permission(self, request):
        """Audit logs cannot be created manually."""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Audit logs cannot be modified."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Only superusers can delete audit logs."""
        return request.user.is_superuser
    
    def colored_action(self, obj):
        """Display action with color coding."""
        colors = {
            'create': '#28a745',  # Green
            'update': '#ffc107',  # Yellow
            'delete': '#dc3545',  # Red
            'login': '#17a2b8',   # Info
            'logout': '#6c757d',  # Gray
            'login_failed': '#dc3545',  # Red
            'email_sent': '#007bff',  # Blue
            'ocr_parse': '#6f42c1',  # Purple
            'file_upload': '#20c997',  # Teal
            'file_delete': '#fd7e14',  # Orange
        }
        
        color = colors.get(obj.action, '#6c757d')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_action_display()
        )
    colored_action.short_description = 'Действие'
    
    def user_link(self, obj):
        """Link to user admin page."""
        if obj.user:
            url = reverse('admin:auth_user_change', args=[obj.user.pk])
            return format_html('<a href="{}">{}</a>', url, obj.username)
        return obj.username or '—'
    user_link.short_description = 'Пользователь'
    
    def object_link(self, obj):
        """Link to object admin page if available."""
        if not obj.content_type or not obj.object_id:
            return '—'
        
        try:
            model_class = obj.content_type.model_class()
            if model_class:
                # Try to get admin URL
                try:
                    instance = model_class.objects.get(pk=obj.object_id)
                    url = reverse(
                        f'admin:{obj.content_type.app_label}_{obj.content_type.model}_change',
                        args=[obj.object_id]
                    )
                    return format_html(
                        '<a href="{}">{}</a>',
                        url,
                        obj.object_repr[:50]
                    )
                except (model_class.DoesNotExist, Exception):
                    # Object deleted or no admin
                    return format_html(
                        '<span style="color: #6c757d;">{} (удалён)</span>',
                        obj.object_repr[:50]
                    )
        except Exception:
            pass
        
        return obj.object_repr[:50] if obj.object_repr else '—'
    object_link.short_description = 'Объект'
    
    def short_description(self, obj):
        """Truncated description."""
        if obj.description:
            return obj.description[:100] + ('...' if len(obj.description) > 100 else '')
        return '—'
    short_description.short_description = 'Описание'
    
    def formatted_changes(self, obj):
        """Format JSON changes for display."""
        if not obj.changes:
            return '—'
        
        try:
            formatted = json.dumps(obj.changes, indent=2, ensure_ascii=False)
            return format_html('<pre style="margin: 0;">{}</pre>', formatted)
        except Exception:
            return str(obj.changes)
    formatted_changes.short_description = 'Изменения'


# Custom filters

class RecentActivityFilter(admin.SimpleListFilter):
    """Filter for recent activity."""
    title = 'Период'
    parameter_name = 'recent'
    
    def lookups(self, request, model_admin):
        return [
            ('1h', 'Последний час'),
            ('24h', 'Последние 24 часа'),
            ('7d', 'Последние 7 дней'),
            ('30d', 'Последние 30 дней'),
        ]
    
    def queryset(self, request, queryset):
        from django.utils import timezone
        from datetime import timedelta
        
        if self.value() == '1h':
            return queryset.filter(timestamp__gte=timezone.now() - timedelta(hours=1))
        elif self.value() == '24h':
            return queryset.filter(timestamp__gte=timezone.now() - timedelta(days=1))
        elif self.value() == '7d':
            return queryset.filter(timestamp__gte=timezone.now() - timedelta(days=7))
        elif self.value() == '30d':
            return queryset.filter(timestamp__gte=timezone.now() - timedelta(days=30))
        
        return queryset


# Add custom filter to admin
AuditLogAdmin.list_filter = list(AuditLogAdmin.list_filter) + [RecentActivityFilter]
