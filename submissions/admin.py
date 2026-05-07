from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin
from django.db.models import QuerySet

from .models import Document, Submission

if TYPE_CHECKING:
    from django.http import HttpRequest


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'status', 'archived_at', 'created_at')
    list_filter = ('status', 'archived_at')
    search_fields = ('name', 'slug')
    ordering = ('-created_at',)

    def get_queryset(self, request: HttpRequest) -> QuerySet[Submission]:
        return Submission.all_objects.all()


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'submission', 'status', 'archived_at', 'created_at')
    list_filter = ('status', 'archived_at')
    search_fields = ('title', 'submission__name')
    ordering = ('-created_at',)
    autocomplete_fields = ('submission',)

    def get_queryset(self, request: HttpRequest) -> QuerySet[Document]:
        return Document.all_objects.select_related('submission')
