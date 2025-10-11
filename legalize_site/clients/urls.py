# Legalize_site/legalize_site/clients/urls.py

# -*- coding: utf-8 -*-

from django.urls import path
from . import views

app_name = 'clients'

urlpatterns = [
    # CRUD для Клиентов (используя CBV)
    path('', views.ClientListView.as_view(), name='client_list'),
    path('client/<int:pk>/', views.ClientDetailView.as_view(), name='client_detail'),
    path('client/add/', views.ClientCreateView.as_view(), name='client_add'),
    path('client/<int:pk>/edit/', views.ClientUpdateView.as_view(), name='client_edit'),
    path('client/<int:pk>/delete/', views.ClientDeleteView.as_view(), name='client_delete'),
    path('api/client-status/<int:pk>/', views.client_status_api, name='client_status_api'),

    # URL для печати
    path('client/<int:pk>/print/', views.client_print_view, name='client_print'),

    # URL для обновления заметок и доступов
    path('client/<int:pk>/update-notes/', views.update_client_notes, name='update_client_notes'),

    # URL для работы с документами
    path('client/<int:client_id>/documents/add/<str:doc_type>/', views.add_document, name='add_document'),
    path('document/<int:pk>/delete/', views.document_delete, name='document_delete'),
    path('document/<int:doc_id>/toggle-verification/', views.toggle_document_verification,
         name='toggle_document_verification'),
    path('<int:pk>/checklist-partial/', views.client_checklist_partial, name='client_checklist_partial'),

    # URL для работы с платежами
    path('client/<int:client_id>/payments/add/', views.add_payment, name='add_payment'),
    path('payment/<int:payment_id>/edit/', views.edit_payment, name='edit_payment'),
    path('payment/<int:payment_id>/delete/', views.delete_payment, name='delete_payment'),

    # --- ИСПРАВЛЕННЫЕ URL ДЛЯ НАПОМИНАНИЙ ---
    # Страница для напоминаний по документам (бывшая общая страница)
    path('reminders/documents/', views.document_reminder_list, name='document_reminder_list'),

    # НОВАЯ страница для напоминаний по оплатам
    path('reminders/payments/', views.payment_reminder_list, name='payment_reminder_list'),

    # Общие URL для действий с напоминаниями
    path('reminders/run-update/', views.run_update_reminders, name='run_update_reminders'),
    path('reminder/<int:reminder_id>/action/', views.reminder_action, name='reminder_action'),

    # URL для калькулятора
    path('calculator/', views.calculator_view, name='calculator'),
]