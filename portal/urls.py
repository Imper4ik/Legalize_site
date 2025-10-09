# portal/urls.py (ФИНАЛЬНАЯ ВЕРСИЯ)

from django.urls import path
from . import views

app_name = 'portal'

urlpatterns = [
    # Главная страница портала теперь будет вести на профиль
    # и будет иметь имя 'root_dashboard'
    path('', views.ProfileDetailView.as_view(), name='root_dashboard'),

    # URL для просмотра и редактирования профиля
    # (Имя 'profile_detail' тоже будет работать)
    path('profile/', views.ProfileDetailView.as_view(), name='profile_detail'),
    path('profile/edit/', views.ProfileUpdateView.as_view(), name='profile_edit'),

    # URL для загрузки документов
    path('upload-document/<str:doc_type>/', views.portal_document_upload, name='portal_document_upload'),
    path('api/checklist-status/', views.checklist_status_api, name='checklist_status_api'),

    # URL для анкеты
    path('application/new/', views.client_application_view, name='client_application'),
    path('application/success/', views.application_success_view, name='application_success'),
]
