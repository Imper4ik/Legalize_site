from django.contrib import admin

from .models import Document, Submission


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('name', 'slug')
    ordering = ('-created_at',)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'submission', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('title', 'submission__name')
    ordering = ('-created_at',)
    autocomplete_fields = ('submission',)
