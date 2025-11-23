# clients/admin.py

from django.contrib import admin

from .models import Client, Document, Payment


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    # Updated to show new, more relevant fields
    list_display = (
        'first_name',
        'last_name',
        'case_number',
        'application_purpose',  # New field
        'status',
        'phone',
        'email',
        'created_at'
    )

    # Replaced 'legal_basis' with 'application_purpose' for filtering
    list_filter = ('status', 'application_purpose', 'language')

    search_fields = ('first_name', 'last_name', 'email', 'phone', 'notes')

    # Making the detail view in the admin more organized
    fieldsets = (
        (
            'Основная информация',
            {'fields': ('first_name', 'last_name', 'email', 'phone', 'citizenship', 'passport_num')},
        ),
        ('Детали подачи', {
            'fields': ('application_purpose', 'basis_of_stay', 'language', 'legal_basis_end_date')
        }),
        ('Статус и Заметки', {
            'fields': ('status', 'notes')
        }),
    )


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('client', 'document_type', 'uploaded_at')
    list_filter = ('document_type',)
    search_fields = ('client__first_name', 'client__last_name')


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 1
    readonly_fields = ('created_at', 'updated_at')
    # Добавляем новые поля в список
    fields = (
        'service_description',
        'total_amount',
        'amount_paid',
        'status',
        'payment_date',
        'payment_method',
        'transaction_id',
        'created_at',
        'updated_at',
    )


