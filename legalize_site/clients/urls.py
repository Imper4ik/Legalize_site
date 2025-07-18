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

    # URL для печати
    path('client/<int:pk>/print/', views.client_print_view, name='client_print'),

    # URL для обновления заметок
    path('client/<int:pk>/update-notes/', views.update_client_notes, name='update_client_notes'),

    # URL для работы с документами
    path('client/<int:client_id>/documents/add/<str:doc_type>/', views.add_document, name='add_document'),
    path('document/<int:pk>/delete/', views.document_delete, name='document_delete'),
    path('document/<int:doc_id>/toggle-verification/', views.toggle_document_verification,
         name='toggle_document_verification'),

    # URL для работы с платежами
    path('client/<int:client_id>/payments/add/', views.add_payment, name='add_payment'),
    path('payment/<int:payment_id>/edit/', views.edit_payment, name='edit_payment'),
    path('payment/<int:payment_id>/delete/', views.delete_payment, name='delete_payment'),

    # URL для напоминаний
    path('reminders/', views.reminder_list, name='reminder_list'),
    path('reminders/create/', views.run_create_reminders, name='create_reminders'),
    path('reminder/<int:reminder_id>/delete/', views.delete_reminder, name='delete_reminder'),

    # URL для калькулятора
    path('calculator/', views.calculator_view, name='calculator'),
]