from django.contrib import admin

# Register your models here.

from .models import Client, Document


class DocumentInline(admin.TabularInline):
    model = Document
    extra = 1


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'citizenship', 'phone', 'email', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('first_name', 'last_name', 'citizenship', 'phone', 'email')
    inlines = [DocumentInline]



@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('doc_type', 'client', 'uploaded_at')

