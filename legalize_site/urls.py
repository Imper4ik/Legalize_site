# legalize_site/urls.py

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.i18n import i18n_patterns
from clients import views
from .cron_views import db_backup

urlpatterns = [
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),
    path('cron/db-backup/', db_backup, name='db_backup'),
]

urlpatterns += i18n_patterns(
    path('accounts/', include('allauth.urls')),
    path('staff/', include('clients.urls', namespace='clients')),
    path('submissions/', include('submissions.urls', namespace='submissions')),

    # Эта строка теперь будет главной страницей после входа
    path('', views.dashboard_redirect_view, name='root_dashboard'),
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
