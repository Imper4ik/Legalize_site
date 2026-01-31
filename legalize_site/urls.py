# legalize_site/urls.py

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.i18n import i18n_patterns
from clients import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),
    # Backup trigger endpoint (не в i18n patterns)
    path('api/backup/trigger/', include([
        path('', lambda request: __import__('core.views.backup_trigger', fromlist=['trigger_backup']).trigger_backup(request)),
        path('status/', lambda request: __import__('core.views.backup_trigger', fromlist=['backup_status']).backup_status(request)),
    ])),
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
