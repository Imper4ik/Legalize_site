from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.i18n import i18n_patterns # <-- Новый импорт

from clients import views

# Эти URL не будут иметь языкового префикса (админка и служебный URL)
urlpatterns = [
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')), # <-- URL для переключения языка
]

# Эти URL будут многоязычными (например, /ru/staff/, /en/portal/)
urlpatterns += i18n_patterns(
    path('accounts/', include('allauth.urls')),
    path('portal/', include('portal.urls', namespace='portal')),
    path('staff/', include('clients.urls', namespace='clients')),
    path('', views.dashboard_redirect, name='root_dashboard'),
    # prefix_default_language=False # Раскомментируйте, если не хотите префикс для языка по умолчанию
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
