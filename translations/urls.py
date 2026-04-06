from django.urls import path
from . import views

app_name = 'translations'

urlpatterns = [
    path('dashboard/', views.studio_dashboard, name='dashboard'),
    path('update/', views.update_translation_api, name='update_api'),
    path('get-api/', views.get_translation_api, name='get_api'),
    path('scan-api/', views.scan_translations_api, name='scan_api'),
    path('toggle-studio/', views.toggle_studio_mode, name='toggle_studio'),
]
