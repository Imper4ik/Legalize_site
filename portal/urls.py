# portal/urls.py (ИСПРАВЛЕННАЯ ВЕРСИЯ)

from django.urls import path
from . import views

app_name = 'portal'

urlpatterns = [
    # URL для просмотра и редактирования профиля
    path('profile/', views.ProfileDetailView.as_view(), name='profile_detail'),
    path('profile/edit/', views.ProfileUpdateView.as_view(), name='profile_edit'),

    # URL для загрузки документов
    path('upload-document/<str:doc_type>/', views.portal_document_upload, name='portal_document_upload'),
    path('api/checklist-status/', views.checklist_status_api, name='checklist_status_api'),

    # --- ИСПРАВЛЕННЫЕ ПУТИ ---
    # Этот путь ведет на страницу с ФОРМОЙ
    path('application/new/', views.client_application_view, name='client_application'),

    # Этот путь ведет на страницу УСПЕХА после заполнения
    path('application/success/', views.application_success_view, name='application_success'),
]