# clients/admin.py

from django.contrib import admin
from .models import Client, Document

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'phone', 'status', 'created_at')
    list_filter = ('status', 'legal_basis', 'language')
    search_fields = ('first_name', 'last_name', 'email', 'phone')

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    # ИСПРАВЛЕНИЕ ЗДЕСЬ: 'doc_type' -> 'document_type'
    list_display = ('client', 'document_type', 'uploaded_at')
    list_filter = ('document_type',)
    search_fields = ('client__first_name', 'client__last_name')