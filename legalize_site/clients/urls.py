from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),  # главная страница
    path('search/', views.client_search, name='client_search'),
    path('clients/', views.client_list, name='client_list'),

    # Клиенты
    path('client/<int:pk>/', views.client_detail, name='client_detail'),
    path('client/<int:pk>/edit/', views.client_edit, name='client_edit'),
    path('client/add/', views.client_add, name='client_add'),



    # Документы
    path('document/<int:pk>/edit/', views.edit_document, name='document_edit'),
    path('document/<int:pk>/delete/', views.document_delete, name='delete_document'),
    path('clients/<int:client_id>/add_document/', views.add_document, name='add_document'),
    path('client/<int:client_id>/update_documents/', views.update_documents, name='update_documents'),
]
