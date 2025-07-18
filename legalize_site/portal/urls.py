from django.urls import path
from . import views

app_name = 'portal'

urlpatterns = [
    # --- ИСПРАВЛЕНО: Используем .as_view() для классовых представлений ---
    path('profile/', views.ProfileDetailView.as_view(), name='profile_detail'),
    path('profile/edit/', views.ProfileUpdateView.as_view(), name='profile_edit'),

    # --- Путь для загрузки документов остается без изменений ---
    path('documents/upload/<str:doc_type>/', views.document_upload, name='document_upload'),
]
