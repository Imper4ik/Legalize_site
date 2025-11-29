from django.urls import path

from . import views

app_name = 'submissions'

urlpatterns = [
    path('', views.SubmissionListView.as_view(), name='submission_list'),
    path('create/', views.SubmissionCreateView.as_view(), name='submission_create'),
    path('quick-create/', views.submission_quick_create, name='submission_quick_create'),
    path('<int:pk>/quick-update/', views.submission_quick_update, name='submission_quick_update'),
    path('<int:pk>/quick-delete/', views.submission_quick_delete, name='submission_quick_delete'),
    path('<int:pk>/', views.SubmissionDetailView.as_view(), name='submission_detail'),

    path('<int:submission_id>/documents/create/', views.DocumentCreateView.as_view(), name='document_create'),
    path('documents/<int:pk>/edit/', views.DocumentUpdateView.as_view(), name='document_edit'),
    path('documents/<int:pk>/delete/', views.DocumentDeleteView.as_view(), name='document_delete'),

    path('api/submissions/', views.submission_api, name='api_submission_list'),
    path('api/submissions/<int:pk>/', views.submission_detail_api, name='api_submission_detail'),
    path('api/submissions/<int:submission_id>/documents/', views.document_api, name='api_document_list'),
    path('api/documents/<int:pk>/', views.document_detail_api, name='api_document_detail'),
]
