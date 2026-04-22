from django.contrib import admin

from .models import Document, Submission


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'status', 'archived_at', 'created_at')
    list_filter = ('status', 'archived_at')
    search_fields = ('name', 'slug')
    ordering = ('-created_at',)
    
    def get_queryset(self, request):
        return Submission.all_objects.all()


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'submission', 'status', 'archived_at', 'created_at')
    list_filter = ('status', 'archived_at')
    search_fields = ('title', 'submission__name')
    ordering = ('-created_at',)
    autocomplete_fields = ('submission',)

    def get_queryset(self, request):
        return Document.all_objects.select_related('submission')
