# portal/urls.py (ФИНАЛЬНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ)

from django.urls import path
from django.views.generic import RedirectView # <-- Добавьте этот импорт
from . import views

app_name = 'portal'

urlpatterns = [
    # --- ДОБАВЛЕНО: Главная страница портала ---
    # При заходе в корень портала, перенаправляем пользователя на его профиль
    path('', RedirectView.as_view(pattern_name='portal:profile_detail'), name='root_dashboard'),

    # URL для просмотра и редактирования профиля
    path('profile/', views.ProfileDetailView.as_view(), name='profile_detail'),
    path('profile/edit/', views.ProfileUpdateView.as_view(), name='profile_edit'),

    # URL для загрузки документов
    path('upload-document/<str:doc_type>/', views.portal_document_upload, name='portal_document_upload'),
    path('api/checklist-status/', views.checklist_status_api, name='checklist_status_api'),

    # URL для анкеты
    path('application/new/', views.client_application_view, name='client_application'),
    path('application/success/', views.application_success_view, name='application_success'),
]