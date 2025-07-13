# clients/urls.py

from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    # Main page
    path('', views.client_list, name='client_list'),

    # Client management
    path('client/add/', views.client_add, name='client_add'),
    path('client/<int:pk>/', views.client_detail, name='client_detail'),
    path('client/<int:pk>/edit/', views.client_edit, name='client_edit'),
    path('client/<int:pk>/delete/', views.client_delete, name='client_delete'),
    path('client/<int:pk>/update_notes/', views.update_client_notes, name='update_client_notes'),
    path('client/<int:pk>/print/', views.client_print_view, name='client_print'),

    # Document management
    path('client/<int:client_id>/add_document/<str:doc_type>/', views.add_document, name='add_document'),
    path('document/<int:pk>/delete/', views.document_delete, name='document_delete'),

    # Payment management
    path('client/<int:client_id>/add_payment/', views.add_payment, name='add_payment'),
    path('payment/<int:payment_id>/edit/', views.edit_payment, name='edit_payment'),
    path('payment/<int:payment_id>/delete/', views.delete_payment, name='delete_payment'),

    # Calculator
    path('calculator/', views.calculator_view, name='calculator'),

    # Reminders
    path('reminders/', views.reminder_list, name='reminder_list'),
    path('reminders/run-check/', views.run_create_reminders, name='run_create_reminders'),
    path('reminder/<int:reminder_id>/delete/', views.delete_reminder, name='delete_reminder'),
    # This is the required URL

    # Authorization
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='clients/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(template_name='clients/logout.html'), name='logout'),
]