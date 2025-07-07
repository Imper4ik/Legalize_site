# clients/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Список клиентов (главная страница)
    path('', views.client_list, name='client_list'),

    # Работа с клиентами
    path('client/add/', views.client_add, name='client_add'),
    path('client/<int:pk>/', views.client_detail, name='client_detail'),
    path('client/<int:pk>/edit/', views.client_edit, name='client_edit'),
    path('client/<int:pk>/delete/', views.client_delete, name='client_delete'),
    path('client/<int:pk>/update_notes/', views.update_client_notes, name='update_client_notes'),
    path('calculator/', views.calculator_view, name='calculator'),
    path('client/<int:pk>/print/', views.client_print_view, name='client_print'),
    path('client/<int:pk>/print/', views.client_print_view, name='client_print'),

    # Работа с документами
    path('client/<int:client_id>/add_document/<str:doc_type>/', views.add_document, name='add_document'),
    path('document/<int:pk>/delete/', views.document_delete, name='document_delete'),
]