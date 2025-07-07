# clients/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Маршрут для главной страницы и списка клиентов
    path('', views.client_list, name='client_list'),

    # Маршруты для работы с клиентами
    path('client/add/', views.client_add, name='client_add'),
    path('client/<int:pk>/', views.client_detail, name='client_detail'),
    path('client/<int:pk>/edit/', views.client_edit, name='client_edit'),

    # Маршруты для работы с документами
    # Этот URL позволяет добавлять файл для конкретного типа документа
    path('client/<int:client_id>/add_document/<str:doc_type>/', views.add_document, name='add_document'),

    # Этот URL удаляет конкретный загруженный файл (по его ID)
    path('document/<int:pk>/delete/', views.document_delete, name='document_delete'),
]