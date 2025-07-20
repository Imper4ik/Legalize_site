from django.urls import path
from . import views

app_name = 'portal'

urlpatterns = [
    # URL для просмотра профиля клиента
    path('profile/', views.ProfileDetailView.as_view(), name='profile_detail'),

    # URL для редактирования профиля клиента
    path('profile/edit/', views.ProfileUpdateView.as_view(), name='profile_edit'),

    path('upload-document/<str:doc_type>/', views.portal_document_upload, name='portal_document_upload'),
    path('api/checklist-status/', views.checklist_status_api, name='checklist_status_api'),
]